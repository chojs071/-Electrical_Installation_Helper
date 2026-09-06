import os
import json
import uuid
import warnings
import base64
import streamlit as st
from openai import OpenAI, APITimeoutError
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError
from streamlit_cookies_controller import CookieController # 🍪 쿠키 컨트롤러 추가

# ⚠️ gotrue 및 기타 DeprecationWarning 경고 무시 설정
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ==========================================
# 🔐 1. Supabase 클라이언트 초기화
# ==========================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("⚠️ `.env` 파일에서 `SUPABASE_URL` 또는 `SUPABASE_ANON_KEY`를 찾을 수 없습니다.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# 🍪 쿠키 매니저 초기화
cookie_controller = CookieController()

# ==========================================
# 🔧 아이디 → 이메일 변환 헬퍼 함수 (상단으로 이동)
# ==========================================
def user_id_to_email(user_id: str) -> str:
    return f"{user_id}@myapp.local"

def email_to_user_id(email: str) -> str:
    return email.split("@")[0]

# ==========================================
# ✅ RLS 오류 해결 및 새로고침 시 로그인 유지 로직
# ==========================================
# 1. 쿠키에서 토큰을 가져와 세션 복원 시도 (새로고침 대응)
access_token = cookie_controller.get("sb_access_token")
refresh_token = cookie_controller.get("sb_refresh_token")
user_id_cookie = cookie_controller.get("sb_user_id")

if access_token and refresh_token and access_token != "":
    try:
        supabase.auth.set_session(access_token, refresh_token)
        # 토큰 유효성 검사
        user_response = supabase.auth.get_user()
        if user_response and user_response.user:
            # 세션 객체 복원 (Mock 객체 사용)
            class SessionMock:
                def __init__(self, a_token, r_token):
                    self.access_token = a_token
                    self.refresh_token = r_token
            
            st.session_state.supabase_session = SessionMock(access_token, refresh_token)
            st.session_state.user = user_response.user
            st.session_state.display_user_id = user_id_cookie or user_response.user.email.split("@")[0]
    except Exception:
        # 토큰이 만료되었거나 유효하지 않으면 쿠키 삭제
        cookie_controller.remove("sb_access_token")
        cookie_controller.remove("sb_refresh_token")
        cookie_controller.remove("sb_user_id")

# 2. 세션 상태에 이미 세션이 있다면 supabase 클라이언트에 다시 설정 (일반 rerun 대비)
if "supabase_session" in st.session_state and st.session_state.supabase_session is not None:
    try:
        supabase.auth.set_session(
            st.session_state.supabase_session.access_token,
            st.session_state.supabase_session.refresh_token
        )
    except Exception:
        st.session_state.supabase_session = None

# ==========================================
# 💡 2. 기본 설정 및 프롬프트
# ==========================================
AI_AVATAR_URL = "https://cdn.phototourl.com/free/2026-07-23-15287eb1-a0dc-42f5-895b-ba283e857248.png"
SIDEBAR_HEADER_IMAGE = "https://cdn.phototourl.com/free/2026-07-23-b00d3b3d-b411-4d1e-a452-24355967b5ce.png"

BASE_SYSTEM_PROMPT = """너는 전기설비 분야의 친절하고 전문적인 AI 도우미야.
반드시 아래에 제공된 [참고 자료]를 바탕으로 정확하게 답변해줘.
참고한 규정의 항과 파일이름은 말하지 않아도 돼.
[참고 자료]에 답이 없거나 관련 내용이 부족하다면, 보유한 지식을 바탕으로 설명하되 자료에 없다는 점을 안내해줘.
나는 전기기능사, 전기(공사)산업기사, 전기(공사)기사를 응시하려는 학생이야.
문제를 만들어 달라는 질문에는 
문제내용
1.
2.
3.
4.
이 형식으로 4지선다로 만들어줘.

만약 사용자가 이미지를 제공했다면, 이미지의 내용(배선도, 기기 사진, 문제 등)을 먼저 정확하게 분석하고 [참고 자료]와 대조하여 전문적으로 답변해줘.
만약 [과거 대화 참고 자료]가 제공된다면, 사용자의 이전 질문 맥락과 내가 previously 답변한 내용을 고려하여 일관성 있고 연속성 있는 답변을 해줘.

수치·단위 표기 규칙: 단위에 LaTeX 수식($...$, \\text 등)을 절대 사용하지 말고 일반 텍스트로만 써줘(예: 50㎟, 2㎜, 3Ω).
표 인용 규칙: [참고 자료]의 표에서 숫자를 인용할 때는 열 제목(지름/단면적/두께 등)을 먼저 확인하고 열에 맞는 단위를 붙여줘(단면적→㎟, 두께·지름→㎜). 열 제목이 불분명하면 "가로×세로" 같은 치수로 추측·단정하지 말고 자료의 표현 그대로 인용해줘.
"""

# ==========================================
# 📂 3. 데이터 폴더 읽기 함수
# ==========================================
def load_relevant_data(prompt: str, data_dir="data", max_files: int = 2, max_chars_per_file: int = 2000):
    """사용자 질문과 관련된 파일만 선별하여 최대 용량만큼만 반환 (토큰 초과 및 타임아웃 방지)"""
    if not os.path.exists(data_dir):
        return ""

    prompt_keywords = set(prompt.lower().replace("알려줘", "").replace("해주세요", "").replace("설명해줘", "").split())
    scored_files = []
    
    for filename in os.listdir(data_dir):
        file_path = os.path.join(data_dir, filename)
        if os.path.isfile(file_path) and filename.endswith(('.txt', '.md', '.json', '.csv')):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                content_lower = content.lower()
                score = sum(1 for keyword in prompt_keywords if len(keyword) > 1 and keyword in content_lower)
                
                scored_files.append((filename, content, score))
            except Exception as e:
                print(f"파일 읽기 오류 ({filename}): {e}")

    scored_files.sort(key=lambda x: x[2], reverse=True)
    
    context_texts = []
    for filename, content, score in scored_files[:max_files]:
        truncated_content = content[:max_chars_per_file] + "\n...(이하 내용 생략)..." if len(content) > max_chars_per_file else content
        context_texts.append(f"--- [참고 파일명: {filename}] ---\n{truncated_content}\n")
    
    if not context_texts and scored_files:
        filename, content, _ = scored_files[0]
        context_texts.append(f"--- [참고 파일명: {filename} (전체 파일 중 일부)] ---\n{content[:2000]}...\n")

    return "\n".join(context_texts)

# ==========================================
# 💾 5. Supabase DB 저장/불러오기 함수
# ==========================================
def load_user_chats_from_db(user_id: str) -> dict:
    try:
        response = supabase.table("user_chats").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
        if response.data:
            chats = {}
            for row in response.data:
                chats[row["id"]] = {
                    "title": row["title"],
                    "messages": row["messages"] or []
                }
            return chats
    except Exception as e:
        st.error(f"대화 목록 불러오기 실패: {e}")
    return None

def save_chat_to_db(user_id: str, chat_id: str, title: str, messages: list):
    try:
        supabase.table("user_chats").upsert({
            "id": chat_id,
            "user_id": user_id,
            "title": title,
            "messages": messages,
            "updated_at": "now()"
        }, on_conflict="id").execute()
    except Exception as e:
        st.error(f"대화 저장 실패: {e}")

# ==========================================
# ✅ 6. 과거 대화 참고 자료 수집 함수
# ==========================================
def collect_reference_chats(chats_dict: dict, selected_ids: list, current_chat_id: str, max_messages_per_chat: int = 5) -> str:
    """선택된 과거 대화들의 내용을 참고 자료 문자열로 구성 (토큰 절약을 위해 개수 축소)"""
    if not selected_ids:
        return ""
    
    ref_parts = []
    for chat_id in selected_ids:
        if chat_id == current_chat_id:
            continue
        if chat_id not in chats_dict:
            continue
        
        chat = chats_dict[chat_id]
        title = chat.get("title", "제목 없음")
        messages = chat.get("messages", [])
        
        recent_messages = messages[-max_messages_per_chat:]
        
        if not recent_messages:
            continue
        
        chat_content = f"\n--- [과거 대화: {title}] ---\n"
        for msg in recent_messages:
            role_kr = "사용자" if msg["role"] == "user" else "AI"
            chat_content += f"{role_kr}: {msg['content']}\n"
        
        ref_parts.append(chat_content)
    
    return "\n".join(ref_parts)

# ==========================================
# 🚀 7. 페이지 기본 설정
# ==========================================
st.set_page_config(page_title="나만의 AI 전기설비 도우미", page_icon=AI_AVATAR_URL, layout="centered")

st.markdown("""
    <style>
    .main { padding-top: 2rem; }
    .stTitle { font-weight: 800; color: #1E293B; }
    .info-box {
        background-color: #F1F5F9;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
        border-left: 5px solid #3B82F6;
    }
    .guest-notice {
        background-color: #FEF3C7;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 15px;
        border-left: 5px solid #F59E0B;
        font-size: 0.9em;
    }
    .ref-notice {
        background-color: #ECFDF5;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 10px;
        border-left: 4px solid #10B981;
        font-size: 0.85em;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🏠 8. 메인 화면 타이틀
# ==========================================
st.title("⚡ 나만의 AI 전기설비 도우미 ⚡")
st.markdown("<p style='text-align: center; color: gray;'>전기 기능사/산업기사/기사 합격을 위한 맞춤형 AI 튜터</p>", unsafe_allow_html=True)

# ==========================================
# 🔍 9. 로그인 상태 확인 및 세션 키 결정
# ==========================================
is_logged_in = "user" in st.session_state and st.session_state.user is not None

if is_logged_in:
    chats_key = f"chats_{st.session_state.user.id}"
    current_chat_key = f"current_chat_id_{st.session_state.user.id}"
    display_user_id = st.session_state.get("display_user_id") or email_to_user_id(st.session_state.user.email)
else:
    chats_key = "guest_chats"
    current_chat_key = "guest_current_chat_id"
    display_user_id = "게스트"

# ==========================================
# 💾 10. 세션 상태 초기화 및 새로고침 대응
# ==========================================

# 🔄 1. 새로고침(F5) 시 DB에서 대화 목록을 다시 불러오는 로직 추가
if is_logged_in and chats_key not in st.session_state:
    db_chats = load_user_chats_from_db(st.session_state.user.id)
    if db_chats:
        st.session_state[chats_key] = db_chats

# 🛡️ 2. 대화 목록 딕셔너리가 없거나 비어있으면 기본 대화 1개 무조건 생성
if chats_key not in st.session_state or not st.session_state[chats_key]:
    initial_id = str(uuid.uuid4())
    st.session_state[chats_key] = {initial_id: {"title": "새로운 대화 1", "messages": []}}

# 🛡️ 3. 현재 선택된 대화 ID가 없거나, 유효하지 않은 ID(삭제됨 등)라면 안전하게 첫 번째 대화로 재설정 (KeyError 방지)
if current_chat_key not in st.session_state or st.session_state[current_chat_key] not in st.session_state[chats_key]:
    st.session_state[current_chat_key] = list(st.session_state[chats_key].keys())[0]

# 4. 과거 대화 참고 선택 초기화
ref_selection_key = f"ref_selection_{display_user_id}"
if ref_selection_key not in st.session_state:
    st.session_state[ref_selection_key] = []

# 5. 최종 변수 할당
current_id = st.session_state[current_chat_key]
current_chat = st.session_state[chats_key][current_id]

# ==========================================
# 👤 11. 사이드바 - 계정 메뉴 & 대화 목록 & 과거 대화 참고
# ==========================================
with st.sidebar:
    st.image(SIDEBAR_HEADER_IMAGE, width="stretch")
    
    if not is_logged_in:
        st.markdown("### 👤 계정 메뉴")
        st.markdown("""
            <div class="guest-notice">
                🎭 <b>게스트 모드</b>로 이용 중입니다.<br>
                💡 로그인하면 대화가 <b>영구 저장</b>됩니다!
            </div>
        """, unsafe_allow_html=True)
        
        auth_tab1, auth_tab2 = st.tabs(["🔑 로그인", "📝 회원가입"])
        
        with auth_tab1:
            with st.form("login_form", clear_on_submit=True):
                user_id = st.text_input("아이디", placeholder="아이디를 입력하세요")
                password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
                submit_button = st.form_submit_button("로그인", width="stretch", type="primary")
                
                if submit_button:
                    if not user_id or not password:
                        st.error("아이디와 비밀번호를 모두 입력해주세요.")
                    else:
                        with st.spinner("로그인 처리 중..."):
                            try:
                                email = user_id_to_email(user_id)
                                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                                if response.user:
                                    st.session_state.user = response.user
                                    st.session_state.supabase_session = response.session
                                    st.session_state.display_user_id = user_id
                                    
                                    # 🍪 쿠키에 토큰 저장
                                    cookie_controller.set("sb_access_token", response.session.access_token)
                                    cookie_controller.set("sb_refresh_token", response.session.refresh_token)
                                    cookie_controller.set("sb_user_id", user_id)
                                    
                                    db_chats = load_user_chats_from_db(response.user.id)
                                    if db_chats:
                                        st.session_state[f"chats_{response.user.id}"] = db_chats
                                    
                                    st.success("로그인 성공!")
                                    st.rerun()
                            except AuthApiError as e:
                                error_msg = str(e).lower()
                                if "rate limit" in error_msg:
                                    st.error("⚠️ 로그인 시도가 너무 많습니다. 1시간 후 다시 시도해 주세요.")
                                elif "invalid login credentials" in error_msg:
                                    st.error("로그인 실패: 아이디 또는 비밀번호가 올바르지 않습니다.")
                                else:
                                    st.error(f"로그인 오류: {e}")
                            except Exception as e:
                                st.error(f"오류가 발생했습니다: {e}")
        
        with auth_tab2:
            with st.form("signup_form", clear_on_submit=True):
                new_user_id = st.text_input("새 아이디", placeholder="3자 이상 영문/숫자")
                new_password = st.text_input("새 비밀번호", type="password", placeholder="6자 이상")
                confirm_password = st.text_input("비밀번호 확인", type="password", placeholder="다시 입력")
                signup_button = st.form_submit_button("회원가입", width="stretch", type="primary")
                
                if signup_button:
                    if not new_user_id or not new_password or not confirm_password:
                        st.error("모든 필드를 입력해주세요.")
                    elif len(new_user_id) < 3:
                        st.error("아이디는 3자 이상이어야 합니다.")
                    elif new_password != confirm_password:
                        st.error("비밀번호가 일치하지 않습니다.")
                    elif len(new_password) < 6:
                        st.error("비밀번호는 6자 이상이어야 합니다.")
                    else:
                        with st.spinner("회원가입 처리 중..."):
                            try:
                                email = user_id_to_email(new_user_id)
                                response = supabase.auth.sign_up({
                                    "email": email,
                                    "password": new_password
                                })
                                
                                if response.user and response.session:
                                    st.session_state.user = response.user
                                    st.session_state.supabase_session = response.session
                                    st.session_state.display_user_id = new_user_id
                                    
                                    # 🍪 쿠키에 토큰 저장
                                    cookie_controller.set("sb_access_token", response.session.access_token)
                                    cookie_controller.set("sb_refresh_token", response.session.refresh_token)
                                    cookie_controller.set("sb_user_id", new_user_id)
                                    
                                    st.success(f"🎉 {new_user_id}님, 환영합니다! 자동으로 로그인되었습니다.")
                                    st.rerun()
                                elif response.user:
                                    login_response = supabase.auth.sign_in_with_password({
                                        "email": email,
                                        "password": new_password
                                    })
                                    if login_response.user:
                                        st.session_state.user = login_response.user
                                        st.session_state.supabase_session = login_response.session
                                        st.session_state.display_user_id = new_user_id
                                        
                                        # 🍪 쿠키에 토큰 저장
                                        cookie_controller.set("sb_access_token", login_response.session.access_token)
                                        cookie_controller.set("sb_refresh_token", login_response.session.refresh_token)
                                        cookie_controller.set("sb_user_id", new_user_id)
                                        
                                        st.success(f"🎉 {new_user_id}님, 환영합니다!")
                                        st.rerun()
                                
                            except AuthApiError as e:
                                error_msg = str(e).lower()
                                if "rate limit" in error_msg:
                                    st.error("⚠️ 회원가입 시도가 너무 많습니다. 1시간 후 다시 시도해 주세요.")
                                elif "user already registered" in error_msg:
                                    st.error("이미 등록된 아이디입니다. 로그인 탭에서 로그인해 주세요.")
                                else:
                                    st.error(f"회원가입 실패: {e}")
                            except Exception as e:
                                st.error(f"오류가 발생했습니다: {e}")
        
        st.markdown("---")
        
    else:
        st.markdown("### 👤 계정 메뉴")
        st.markdown(f"### 👋 안녕하세요, **{display_user_id}**님!")
        
        if st.button("🚪 로그아웃", width="stretch", type="secondary"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.supabase_session = None
            st.session_state.display_user_id = None
            
            # 🍪 쿠키 삭제
            cookie_controller.remove("sb_access_token")
            cookie_controller.remove("sb_refresh_token")
            cookie_controller.remove("sb_user_id")
            
            st.rerun()
        
        st.markdown("---")
    
    # 나머지 사이드바 및 UI 코드는 기존과 동일하게 유지됩니다.
    st.markdown("### 💬 대화 목록")
    
    if st.button("➕ 새 대화 시작", width="stretch", type="primary"):
        new_id = str(uuid.uuid4())
        new_title = f"새로운 대화 {len(st.session_state[chats_key]) + 1}"
        st.session_state[chats_key][new_id] = {"title": new_title, "messages": []}
        st.session_state[current_chat_key] = new_id
        st.rerun()
    
    st.markdown("---")
    
    chat_options = {cid: info["title"] for cid, info in st.session_state[chats_key].items()}
    
    if current_id not in chat_options:
        st.session_state[current_chat_key] = list(chat_options.keys())[0]
        st.rerun()
    
    selected_id = st.radio(
        "대화 선택",
        options=list(chat_options.keys()),
        format_func=lambda x: chat_options[x],
        index=list(chat_options.keys()).index(current_id)
    )
    
    if selected_id != current_id:
        st.session_state[current_chat_key] = selected_id
        st.rerun()
    
    if is_logged_in:
        st.markdown("---")
        st.markdown("### 📚 과거 대화 참고")
        st.markdown("""
            <div class="ref-notice">
                💡 체크한 과거 대화 내용을 AI가 참고하여 답변합니다.<br>
                (최대 3개 선택 가능, 각 대화의 최근 5개 메시지만 참고)
            </div>
        """, unsafe_allow_html=True)
        
        other_chats = {cid: info for cid, info in st.session_state[chats_key].items() if cid != current_id}
        
        if not other_chats:
            st.info("참고할 다른 대화가 없습니다.")
        else:
            current_selection = st.session_state[ref_selection_key]
            current_selection = [cid for cid in current_selection if cid in other_chats]
            
            new_selection = []
            for cid, info in other_chats.items():
                is_checked = cid in current_selection
                disabled = (not is_checked) and (len(current_selection) >= 3)
                
                checked = st.checkbox(
                    f"📖 {info['title']}",
                    value=is_checked,
                    key=f"ref_chk_{cid}",
                    disabled=disabled,
                    help="이 대화를 참고 자료로 포함"
                )
                if checked:
                    new_selection.append(cid)
            
            if new_selection != current_selection:
                st.session_state[ref_selection_key] = new_selection
                st.rerun()
            
            if current_selection:
                st.caption(f"✨ {len(current_selection)}개 대화 참고 중")
            else:
                st.caption("참고할 대화를 선택하지 않았습니다.")

    # ==========================================
    # 🖼️ 이미지 전용 입력 섹션
    # ==========================================
    st.markdown("---")
    st.markdown("### 🖼️ 이미지 입력")
    st.markdown("""
        <div class="ref-notice">
            💡 분석하거나 참고할 이미지를 업로드하세요.<br>
            (지원 형식: PNG, JPG, JPEG, WEBP)
        </div>
    """, unsafe_allow_html=True)
    
    # 전송 후 업로더를 초기화하기 위해 동적 키 사용
    img_counter = st.session_state.get("img_counter", 0)
    uploaded_image = st.file_uploader(
        "이미지 파일 선택",
        type=["png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
        key=f"sidebar_image_uploader_{img_counter}"
    )
    
    if uploaded_image is not None:
        st.session_state.current_uploaded_image = uploaded_image

    if "current_uploaded_image" in st.session_state and st.session_state.current_uploaded_image is not None:
        st.image(st.session_state.current_uploaded_image, caption="업로드된 이미지 미리보기", width="stretch")
        st.success("✅ 이미지가 성공적으로 업로드되었습니다. (메시지 입력 시 함께 분석됩니다)")

    # ==========================================
    # 📁 수동으로 대화 백업 & 불러오기
    # ==========================================
    st.markdown("---")
    st.markdown("### 📁 수동으로 대화 백업 & 불러오기")
    
    current_messages = current_chat["messages"]
    json_data = json.dumps(current_messages, ensure_ascii=False, indent=2)
    
    st.download_button(
        label="📥 현재 대화 JSON 저장",
        data=json_data,
        file_name=f"{current_chat['title']}_{display_user_id}.json",
        mime="application/json",
        width="stretch",
        disabled=len(current_messages) == 0
    )
    
    uploaded_file = st.file_uploader("📤 JSON 대화 불러오기", type=["json"], key="json_file_uploader")
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get("last_uploaded_file") != file_id:
            try:
                loaded_messages = json.load(uploaded_file)
                if isinstance(loaded_messages, list):
                    imported_id = str(uuid.uuid4())
                    st.session_state[chats_key][imported_id] = {
                        "title": f"📂 {os.path.splitext(uploaded_file.name)[0]}",
                        "messages": loaded_messages
                    }
                    st.session_state[current_chat_key] = imported_id
                    st.session_state.last_uploaded_file = file_id
                    st.success("대화를 성공적으로 불러왔습니다!")
                    st.rerun()
            except Exception as e:
                st.error(f"파일 읽기 오류: {e}")

# ==========================================
# 💬 12. 메인 영역 - 채팅 UI
# ==========================================
if not is_logged_in:
    st.markdown("""
        <div class="guest-notice">
            🎭 <b>게스트 모드</b>로 이용 중입니다. 대화는 브라우저를 닫으면 사라집니다.<br>
            👉 좌측 사이드바에서 <b>회원가입</b> 후 로그인하면 대화가 영구 저장됩니다!
        </div>
    """, unsafe_allow_html=True)

if is_logged_in and st.session_state[ref_selection_key]:
    ref_titles = [st.session_state[chats_key][cid]["title"] 
                  for cid in st.session_state[ref_selection_key] 
                  if cid in st.session_state[chats_key]]
    if ref_titles:
        st.markdown(f"""
            <div class="ref-notice">
                📚 <b>참고 중인 과거 대화:</b> {', '.join(ref_titles)}
            </div>
        """, unsafe_allow_html=True)

st.caption(f"📌 **현재 대화:** {current_chat['title']} | 👤 {display_user_id}")

if len(current_chat["messages"]) == 0:
    st.markdown("""
        <div class="info-box">
            👋 <b>반갑습니다!</b> 무엇이든 물어보세요.<br>
            예시: <i>"접지공사 종류에 대해 알려줘"</i>
        </div>
    """, unsafe_allow_html=True)

# ✅ 멀티모달(이미지+텍스트) 메시지 렌더링 처리
for message in current_chat["messages"]:
    avatar = "👤" if message["role"] == "user" else AI_AVATAR_URL
    with st.chat_message(message["role"], avatar=avatar):
        if isinstance(message["content"], list):
            for item in message["content"]:
                if item["type"] == "text":
                    st.markdown(item["text"])
                elif item["type"] == "image_url":
                    st.image(item["image_url"]["url"], width="stretch")
        else:
            st.markdown(message["content"])

if prompt := st.chat_input("질문을 입력하세요 (이미지 첨부가능)"):
    if len(current_chat["messages"]) == 0:
        current_chat["title"] = prompt[:15] + "..." if len(prompt) > 15 else prompt
    
    # 사용자 메시지 구성 (멀티모달 지원)
    user_content = []
    if prompt.strip():
        user_content.append({"type": "text", "text": prompt})
    
    # 업로드된 이미지가 있으면 Base64 인코딩하여 메시지에 추가
    if "current_uploaded_image" in st.session_state and st.session_state.current_uploaded_image is not None:
        img_file = st.session_state.current_uploaded_image
        img_bytes = img_file.read()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        mime_type = img_file.type if img_file.type else "image/jpeg"
        
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{img_base64}"}
        })
        
        # 전송 후 세션 및 업로더 초기화 (중복 전송 방지)
        del st.session_state.current_uploaded_image
        st.session_state.img_counter = st.session_state.get("img_counter", 0) + 1

    # content가 리스트인지 문자열인지에 따라 포맷팅 (DB 호환성 유지)
    if len(user_content) == 1 and user_content[0]["type"] == "text":
        final_user_message = {"role": "user", "content": user_content[0]["text"]}
    else:
        final_user_message = {"role": "user", "content": user_content}

    current_chat["messages"].append(final_user_message)
    
    if is_logged_in:
        save_chat_to_db(st.session_state.user.id, current_id, current_chat["title"], current_chat["messages"])

    with st.chat_message("user", avatar="👤"):
        if isinstance(final_user_message["content"], list):
            for item in final_user_message["content"]:
                if item["type"] == "text":
                    st.markdown(item["text"])
                elif item["type"] == "image_url":
                    st.image(item["image_url"]["url"], width="stretch")
        else:
            st.markdown(final_user_message["content"])
    
    with st.chat_message("assistant", avatar=AI_AVATAR_URL):
        try:
            api_key = os.getenv("NVIDIA_API_KEY")
            if not api_key:
                st.error("⚠️ NVIDIA_API_KEY가 설정되지 않았습니다.")
            else:
                client = OpenAI(
                    base_url="https://ollama.com/v1", 
                    api_key=api_key,
                    timeout=120.0
                )
                
                data_context = load_relevant_data(prompt)
                
                ref_context = ""
                if is_logged_in and st.session_state[ref_selection_key]:
                    ref_context = collect_reference_chats(
                        st.session_state[chats_key],
                        st.session_state[ref_selection_key],
                        current_id
                    )
                
                system_prompt = BASE_SYSTEM_PROMPT
                if data_context:
                    system_prompt += f"\n\n[참고 자료]\n{data_context}"
                if ref_context:
                    system_prompt += f"\n\n[과거 대화 참고 자료]\n{ref_context}"
                
                max_history_messages = 10
                recent_messages = current_chat["messages"][-max_history_messages:]
                
                messages_to_send = [{"role": "system", "content": system_prompt}] + recent_messages
                
                # ✅ 기존에 사용하시던 비전 지원 모델명 유지 (Gemma 비전 모델)
                stream = client.chat.completions.create(
                    model="gemma4:31b-cloud",  # 필요시 실제 NVIDIA API의 정확한 Gemma 비전 모델명으로 수정 가능 (예: google/gemma-3-27b-it)
                    messages=messages_to_send,
                    stream=True
                )
                response_content = st.write_stream(stream)
                current_chat["messages"].append({"role": "assistant", "content": response_content})
                
                if is_logged_in:
                    save_chat_to_db(st.session_state.user.id, current_id, current_chat["title"], current_chat["messages"])
                    
        except APITimeoutError:
            st.error("⏱️ **요청 시간 초과**: AI 서버 응답이 느리거나 전송된 데이터 양이 너무 많습니다. 질문을 더 간결하게 하거나, '과거 대화 참고' 선택을 줄여주세요.")
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
