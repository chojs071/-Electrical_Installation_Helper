import os
import json
import uuid
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

# 💡 사용할 이미지 URL 및 기본 지침 지정
AI_AVATAR_URL = "https://cdn.phototourl.com/free/2026-07-23-15287eb1-a0dc-42f5-895b-ba283e857248.png"
SIDEBAR_HEADER_IMAGE = "https://cdn.phototourl.com/free/2026-07-23-b00d3b3d-b411-4d1e-a452-24355967b5ce.png"

BASE_SYSTEM_PROMPT = """너는 전기설비 분야의 친절하고 전문적인 AI 도우미야.
반드시 아래에 제공된 [참고 자료]를 바탕으로 정확하게 답변해줘.
[참고 자료]에 답이 없거나 관련 내용이 부족하다면, 보유한 지식을 바탕으로 설명하되 자료에 없다는 점을 안내해줘.
"""

# 📂 data 폴더 내 텍스트/문서 파일 읽기 함수
def load_data_folder(data_dir="data"):
    if not os.path.exists(data_dir):
        os.makedirs(data_dir) # data 폴더가 없으면 자동 생성
        return ""

    context_texts = []
    # data 폴더 안의 모든 파일 탐색
    for filename in os.listdir(data_dir):
        file_path = os.path.join(data_dir, filename)
        
        # 텍스트 관련 파일만 읽기 (.txt, .md, .json, .csv 등)
        if os.path.isfile(file_path) and filename.endswith(('.txt', '.md', '.json', '.csv')):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    context_texts.append(f"--- [파일명: {filename}] ---\n{content}\n")
            except Exception as e:
                print(f"파일 읽기 오류 ({filename}): {e}")

    return "\n".join(context_texts)

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="나만의 AI 전기설비 도우미",
    page_icon=AI_AVATAR_URL,
    layout="centered"
)

# 2. .env 파일 로드
load_dotenv()
api_key = os.getenv("NVIDIA_API_KEY")

# 3. Custom CSS 스타일링
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
    </style>
""", unsafe_allow_html=True)

# 4. 세션 상태(Session State) 초기화
if "chats" not in st.session_state:
    initial_id = str(uuid.uuid4())
    st.session_state.chats = {
        initial_id: {"title": "새로운 대화 1", "messages": []}
    }
    st.session_state.current_chat_id = initial_id

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = list(st.session_state.chats.keys())[0]

current_id = st.session_state.current_chat_id
current_chat = st.session_state.chats[current_id]

# 5. 엔비디아 OpenAI 클라이언트 설정
if not api_key:
    st.error("⚠️ `.env` 파일에서 `NVIDIA_API_KEY`를 찾을 수 없습니다. 키를 설정해 주세요!")
    st.stop()

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

# 6. 사이드바 - 대화 목록 관리 & JSON 저장/불러오기
with st.sidebar:
    st.image(SIDEBAR_HEADER_IMAGE, use_container_width=True)
    st.title("💬 대화 목록")
    
    if st.button("➕ 새 대화 시작", use_container_width=True, type="primary"):
        new_id = str(uuid.uuid4())
        new_title = f"새로운 대화 {len(st.session_state.chats) + 1}"
        st.session_state.chats[new_id] = {"title": new_title, "messages": []}
        st.session_state.current_chat_id = new_id
        st.rerun()

    st.markdown("---")

    chat_options = {cid: info["title"] for cid, info in st.session_state.chats.items()}
    selected_id = st.radio(
        "대화 선택",
        options=list(chat_options.keys()),
        format_func=lambda x: chat_options[x],
        index=list(chat_options.keys()).index(current_id)
    )

    if selected_id != current_id:
        st.session_state.current_chat_id = selected_id
        st.rerun()

    st.markdown("---")
    st.subheader("📁 대화 백업 & 불러오기")

    current_messages = current_chat["messages"]
    json_data = json.dumps(current_messages, ensure_ascii=False, indent=2)
    
    st.download_button(
        label="📥 현재 대화 JSON 저장",
        data=json_data,
        file_name=f"{current_chat['title']}.json",
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
                    file_title = os.path.splitext(uploaded_file.name)[0]
                    st.session_state.chats[imported_id] = {
                        "title": f"📂 {file_title}",
                        "messages": loaded_messages
                    }
                    st.session_state.current_chat_id = imported_id
                    st.session_state.last_uploaded_file = file_id
                    st.success("대화를 성공적으로 불러왔습니다!")
                    st.rerun()
                else:
                    st.error("올바른 대화 내역 JSON 형식이 아닙니다.")
            except Exception as e:
                st.error(f"파일 읽기 오류: {e}")

# 7. 메인 화면 타이틀 및 안내
st.title("⚡ 나만의 AI 전기설비 도우미 ⚡")
st.caption(f"📌 **현재 대화:** {current_chat['title']}")

if len(current_chat["messages"]) == 0:
    st.markdown("""
        <div class="info-box">
            👋 <b>반갑습니다!</b> 무엇이든 물어보세요.<br>
            예시: <i>"접지공사 종류에 대해 알려줘"</i>
        </div>
    """, unsafe_allow_html=True)

# 8. 이전 대화 기록 출력
for message in current_chat["messages"]:
    avatar = "👤" if message["role"] == "user" else AI_AVATAR_URL
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

# 9. 사용자 입력 및 AI 스트리밍 응답 처리
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    if len(current_chat["messages"]) == 0:
        short_title = prompt[:15] + "..." if len(prompt) > 15 else prompt
        current_chat["title"] = short_title

    current_chat["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AI_AVATAR_URL):
        try:
            # 📄 data 폴더 내부 문서 읽어오기
            data_context = load_data_folder()
            
            # 지침 + data 문서 데이터 조합
            system_prompt = BASE_SYSTEM_PROMPT
            if data_context:
                system_prompt += f"\n\n[참고 자료]\n{data_context}"

            messages_to_send = [
                {"role": "system", "content": system_prompt}
            ] + current_chat["messages"]

            stream = client.chat.completions.create(
                model="google/diffusiongemma-26b-a4b-it",
                messages=messages_to_send,
                stream=True
            )
            
            response_content = st.write_stream(stream)
            current_chat["messages"].append({"role": "assistant", "content": response_content})
            
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")