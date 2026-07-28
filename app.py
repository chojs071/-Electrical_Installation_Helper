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

# ✅ RLS 오류 해결: Streamlit 재실행 시 로그인 세션(토큰) 복원
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
반드시 아래에 제공된 [참고 자료]를 바탕으로 정확하게 답변해줘. 참고한 규정의 항과 파일이름은 말하지 않아도 돼.
[참고 자료]에 답이 없거나 관련 내용이 부족하다면, 보유한 지식을 바탕으로 설명하되 자료에 없다는 점을 안내해줘.
나는 전기기능사, 전기(공사)산업기사, 전기(공사)기사를 응시하려는 학생이야.
문제를 만들어 달라는 질문에는 
문제내용
1.
2.
3.
4.
이 형식으로 4지선다로 만들어줘.

만약 [과거 대화 참고 자료]가 제공된다면, 사용자의 이전 질문 맥락과 내가 previously 답변한 내용을 고려하여 일관성 있고 연속성 있는 답변을 해줘.
사용자가 이미지를 업로드하면, 이미지에 포함된 내용(배선도, 기기 사진, 문제 등)을 분석하여 전기설비 관점에서 친절하게 설명해줘.
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
# 🔧 4. 아이디 → 이메일 변환 헬퍼 함수
# ==========================================
def user_id_to_email(user_id: str) -> str:
    return f"{user_id}@myapp.local"

def email_to_user_id(email: str) -> str:
    return email.split("@")[0]

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
    .stFileUploader { margin-bottom: 0px; }
    .stFileUploader > div { padding: 0px; }
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
# 💾 10. 세션 상태 초기화
# ==========================================
if chats_key not in st.session_state:
    initial_id = str(uuid.uuid4())
    st.session_state[chats_key] = {initial_id: {"title": "새로운 대화 1", "messages": []}}
    st.session_state[current_chat_key] = initial_id

if current_chat_key not in st.session_state:
    st.session_state[current_chat_key] = list(st.session_state[chats_key].keys())[0]

ref_selection_key = f"ref_selection_{display_user_id}"
if ref_selection_key not in st.session_state:
    st.session_state[ref_selection_key] = []

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
            st.rerun()
        
        st.markdown("---")
    
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
    
    uploaded_file = st.file_uploader("📤 JSON 대화 불러오기", type=["json"])
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
# 💬 12. 메인 영역 - 채팅 UI 및 하단 고정 입력창
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
            예시: <i>"접지공사 종류에 대해 알려줘"</i> 또는 <i>아래 [+] 아이콘으로 전기 배선도 사진을 업로드하세요.</i>
        </div>
    """, unsafe_allow_html=True)

# ✅ 기존 메시지 렌더링 (이미지 포함 지원)
for message in current_chat["messages"]:
    avatar = "👤" if message["role"] == "user" else AI_AVATAR_URL
    with st.chat_message(message["role"], avatar=avatar):
        if "image" in message:
            st.image(f"data:{message['image']['mime_type']};base64,{message['image']['base64']}", width=300)
        st.markdown(message["content"])

# ==========================================
# 📌 하단 고정 1:3 비율 입력창 레이아웃
# ==========================================
st.markdown("""
    <style>
    /* 채팅 메시지가 하단 입력창에 가려지지 않도록 하단 여백 확보 */
    .block-container {
        padding-bottom: 100px !important;
    }
    /* 하단 입력 영역을 화면 하단에 고정 (Sticky) */
    .bottom-input-bar {
        position: sticky;
        bottom: 0;
        background-color: #ffffff; /* 배경색을 흰색으로 하여 스크롤 시 가독성 확보 */
        padding: 15px 5px 10px 5px;
        border-top: 2px solid #e2e8f0;
        z-index: 999;
        margin-top: 20px;
    }
    /* 파일 업로더 라벨 숨기고 컴팩트하게 조정 */
    .stFileUploader [data-testid="stFileUploaderDropzone"] {
        min-height: 42px !important;
        padding: 5px !important;
        border: 1px dashed #cbd5e1 !important;
        border-radius: 8px !important;
    }
    .stFileUploader label {
        display: none !important; /* '이미지 첨부' 텍스트 숨김 */
    }
    /* 채팅 입력창 높이 및 스타일 조정 */
    .stChatInput textarea {
        max-height: 100px !important;
    }
    </style>
""", unsafe_allow_html=True)

# 1:3 비율로 컬럼 분할
col_img, col_txt = st.columns([1, 3])

with col_img:
    uploader_key = f"uploader_{current_id}_{len(current_chat['messages'])}"
    uploaded_image = st.file_uploader(
        "📎",  # 아이콘만 표시
        type=["png", "jpg", "jpeg"], 
        key=uploader_key,
        label_visibility="collapsed",
        help="이미지 첨부 (클릭하여 파일 선택)"
    )

with col_txt:
    prompt = st.chat_input("메시지를 입력하세요... (Enter로 전송)")

# ==========================================
# 🚀 전송 로직
# ==========================================
if prompt or uploaded_image is not None:
    if len(current_chat["messages"]) == 0:
        current_chat["title"] = (prompt[:15] + "...") if prompt else "이미지 분석"
    
    new_message = {"role": "user", "content": prompt if prompt else "이 이미지에 대해 분석해 주세요."}
    
    if uploaded_image is not None:
        image_bytes = uploaded_image.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        new_message["image"] = {
            "base64": image_base64,
            "mime_type": uploaded_image.type
        }
    
    current_chat["messages"].append(new_message)
    if is_logged_in:
        save_chat_to_db(st.session_state.user.id, current_id, current_chat["title"], current_chat["messages"])

    # 사용자 메시지 화면에 즉시 표시
    with st.chat_message("user", avatar="👤"):
        if "image" in new_message:
            st.image(f"data:{new_message['image']['mime_type']};base64,{new_message['image']['base64']}", width=300)
        st.markdown(new_message["content"])
    
    # AI 응답 처리
    with st.chat_message("assistant", avatar=AI_AVATAR_URL):
        try:
            api_key = os.getenv("NVIDIA_API_KEY")
            if not api_key:
                st.error("⚠️ NVIDIA_API_KEY가 설정되지 않았습니다.")
            else:
                client = OpenAI(
                    base_url="https://integrate.api.nvidia.com/v1", 
                    api_key=api_key,
                    timeout=120.0
                )
                
                data_context = load_relevant_data(prompt if prompt else "이미지 분석")
                
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
                
                messages_to_send = [{"role": "system", "content": system_prompt}]
                for msg in recent_messages:
                    if msg["role"] == "user" and "image" in msg:
                        messages_to_send.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": msg["content"]},
                                {"type": "image_url", "image_url": {"url": f"data:{msg['image']['mime_type']};base64,{msg['image']['base64']}"}}
                            ]
                        })
                    else:
                        messages_to_send.append({"role": msg["role"], "content": msg["content"]})
                
                stream = client.chat.completions.create(
                    model="google/gemma-4-31b-it", # 또는 사용 중인 모델명
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