import type { Chat, ChatMessage } from "./types";

/** 현재 대화를 JSON 파일로 내보내기 (원본 st.download_button 대응) */
export function exportChatToJson(chat: Chat, displayUserId: string): void {
  const json = JSON.stringify(chat.messages, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${chat.title}_${displayUserId}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

/** JSON 파일에서 대화 불러오기 */
export function importChatFromJson(file: File): Promise<ChatMessage[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("파일을 읽을 수 없습니다."));
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        if (!Array.isArray(parsed)) {
          throw new Error("대화 형식이 올바르지 않습니다.");
        }
        resolve(parsed as ChatMessage[]);
      } catch (e) {
        reject(e instanceof Error ? e : new Error(String(e)));
      }
    };
    reader.readAsText(file);
  });
}
