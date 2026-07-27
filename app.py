import os
import json
import uuid
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
from gotrue.errors import AuthApiError

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
        # 세션이 만료된 경우 등을 대비해 예외 처리
        st.session_state.supabase_session = None

# ==========================================
# 💡 2. 기본 설정 및 프롬프트
# ==========================================
AI_AVATAR_URL = "https://cdn.phototourl.com/free/2026-07-23-15287eb1-a0dc-42f5-895b-ba283e857248.png"
SIDEBAR_HEADER_IMAGE = "https://cdn.phototourl.com/free/2026-07-23-b00d3b3d-b411-4d1e-a452-24355967b5ce.png"

BASE_SYSTEM_PROMPT = """너는 전기설비 분야의 친절하고 전문적인 AI 도우미야.
반드시 아래에 제공된 [참고 자료]를 바탕으로 정확하게 답변해줘. 그리고 참고한 파일명을 알려줘.
[참고 자료]에 답이 없거나 관련 내용이 부족하다면, 보유한 지식을 바탕으로 설명하되 자료에 없다는 점을 안내해줘.
나는 전기기능사, 전기(공사)산업기사, 전기(공사)기사를 응시하려는 학생이야.
문제를 만들어 달라는 질문에는 
문제내용
1.
2.
3.
4.
이 형식으로 4지선다로 만들어줘.
"""

# ==========================================
# 📂 3. 데이터 폴더 읽기 함수
# ==========================================
def load_data_folder(data_dir="data"):
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        return ""

    context_texts = []
    for filename in os.listdir(data_dir):
        file_path = os.path.join(data_dir, filename)
        if os.path.isfile(file_path) and filename.endswith(('.txt', '.md', '.json', '.csv')):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    context_texts.append(f"--- [파일명: {filename}] ---\n{content}\n")
            except Exception as e:
                print(f"파일 읽기 오류 ({filename}): {e}")

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
    """사용자의 대화 내역을 DB에서 불러옴"""
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
    """현재 대화 내역을 DB에 저장 (Upsert)"""
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
# 🚀 6. 페이지 기본 설정
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
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🏠 7. 메인 화면 타이틀
# ==========================================
st.title("⚡ 나만의 AI 전기설비 도우미 ⚡")
st.markdown("<p style='text-align: center; color: gray;'>전기 기능사/산업기사/기사 합격을 위한 맞춤형 AI 튜터</p>", unsafe_allow_html=True)

# ==========================================
# 🔍 8. 로그인 상태 확인 및 세션 키 결정
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
# 💾 9. 세션 상태 초기화
# ==========================================
if chats_key not in st.session_state:
    initial_id = str(uuid.uuid4())
    st.session_state[chats_key] = {initial_id: {"title": "새로운 대화 1", "messages": []}}
    st.session_state[current_chat_key] = initial_id

if current_chat_key not in st.session_state:
    st.session_state[current_chat_key] = list(st.session_state[chats_key].keys())[0]

current_id = st.session_state[current_chat_key]
current_chat = st.session_state[chats_key][current_id]

# ==========================================
# 👤 10. 사이드바 - 계정 메뉴 & 대화 목록
# ==========================================
with st.sidebar:
    st.image(SIDEBAR_HEADER_IMAGE, use_container_width=True)
    
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
                submit_button = st.form_submit_button("로그인", use_container_width=True, type="primary")
                
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
                                    # ✅ RLS 오류 해결: 세션 객체 전체 저장
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
                signup_button = st.form_submit_button("회원가입", use_container_width=True, type="primary")
                
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
                                    # ✅ RLS 오류 해결: 세션 객체 전체 저장
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
        
        if st.button("🚪 로그아웃", use_container_width=True, type="secondary"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.supabase_session = None # ✅ 세션 토큰도 함께 삭제
            st.session_state.display_user_id = None
            st.rerun()
        
        st.markdown("---")
    
    st.title("💬 대화 목록")
    
    if st.button("➕ 새 대화 시작", use_container_width=True, type="primary"):
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
    
    st.markdown("---")
    st.subheader("📁 대화 백업 & 불러오기")
    
    current_messages = current_chat["messages"]
    json_data = json.dumps(current_messages, ensure_ascii=False, indent=2)
    
    st.download_button(
        label="📥 현재 대화 JSON 저장",
        data=json_data,
        file_name=f"{current_chat['title']}_{display_user_id}.json",
        mime="application/json",
        use_container_width=True,
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
# 💬 11. 메인 영역 - 채팅 UI
# ==========================================
if not is_logged_in:
    st.markdown("""
        <div class="guest-notice">
            🎭 <b>게스트 모드</b>로 이용 중입니다. 대화는 브라우저를 닫으면 사라집니다.<br>
            👉 좌측 사이드바에서 <b>회원가입</b> 후 로그인하면 대화가 영구 저장됩니다!
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

for message in current_chat["messages"]:
    avatar = "👤" if message["role"] == "user" else AI_AVATAR_URL
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

if prompt := st.chat_input("무엇을 도와드릴까요?"):
    if len(current_chat["messages"]) == 0:
        current_chat["title"] = prompt[:15] + "..." if len(prompt) > 15 else prompt
    
    current_chat["messages"].append({"role": "user", "content": prompt})
    
    if is_logged_in:
        save_chat_to_db(st.session_state.user.id, current_id, current_chat["title"], current_chat["messages"])

    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
    
    with st.chat_message("assistant", avatar=AI_AVATAR_URL):
        try:
            api_key = os.getenv("NVIDIA_API_KEY")
            if not api_key:
                st.error("⚠️ NVIDIA_API_KEY가 설정되지 않았습니다.")
            else:
                client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
                
                data_context = load_data_folder()
                system_prompt = BASE_SYSTEM_PROMPT + (f"\n\n[참고 자료]\n{data_context}" if data_context else "")
                messages_to_send = [{"role": "system", "content": system_prompt}] + current_chat["messages"]
                
                stream = client.chat.completions.create(
                    model="google/gemma-4-31b-it",
                    messages=messages_to_send,
                    stream=True
                )
                response_content = st.write_stream(stream)
                current_chat["messages"].append({"role": "assistant", "content": response_content})
                
                if is_logged_in:
                    save_chat_to_db(st.session_state.user.id, current_id, current_chat["title"], current_chat["messages"])
                    
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")