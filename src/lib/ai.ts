import { AI_BASE_URL, AI_MODEL, AI_TIMEOUT_MS } from "./constants";
import type { ChatMessage } from "./types";

export interface StreamChatOptions {
  systemPrompt: string;
  messages: ChatMessage[];
  onDelta?: (text: string) => void;
}

const TIMEOUT_MESSAGE =
  "⏱️ **요청 시간 초과**: AI 서버 응답이 느리거나 전송된 데이터 양이 너무 많습니다. 질문을 더 간결하게 하거나, '과거 대화 참고' 선택을 줄여주세요.";

/** OpenAI 호환 API로 스트리밍 답변 요청 (원본과 동일: /v1/chat/completions, stream) */
export async function streamChatCompletion({
  systemPrompt,
  messages,
  onDelta,
}: StreamChatOptions): Promise<string> {
  const apiKey = import.meta.env.VITE_NVIDIA_API_KEY;
  if (!apiKey) {
    throw new Error("⚠️ NVIDIA_API_KEY가 설정되지 않았습니다.");
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, AI_TIMEOUT_MS);

  try {
    const res = await fetch(`${AI_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: AI_MODEL,
        messages: [{ role: "system", content: systemPrompt }, ...messages],
        stream: true,
      }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`AI API 오류 (${res.status}): ${body.slice(0, 200)}`);
    }
    if (!res.body) {
      throw new Error("이 브라우저는 스트리밍 응답을 지원하지 않습니다.");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let full = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        for (const line of part.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (!data || data === "[DONE]") continue;
          try {
            const parsed = JSON.parse(data);
            const delta: string =
              parsed?.choices?.[0]?.delta?.content ??
              parsed?.choices?.[0]?.message?.content ??
              "";
            if (delta) {
              full += delta;
              onDelta?.(delta);
            }
          } catch {
            // 불완전한 JSON 청크는 무시
          }
        }
      }
    }
    return full;
  } catch (e) {
    if (timedOut) throw new Error(TIMEOUT_MESSAGE);
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("요청이 중단되었습니다.");
    }
    // 브라우저 fetch 네트워크 실패(CORS 차단, DNS, 오프라인, 광고차단 등)는
    // 상태 코드 없이 "Failed to fetch" / "NetworkError" 로만 떨어지므로 안내문을 붙임
    const raw = e instanceof Error ? e.message : String(e);
    if (
      raw.toLowerCase().includes("failed to fetch") ||
      raw.toLowerCase().includes("networkerror") ||
      raw.toLowerCase().includes("load failed")
    ) {
      throw new Error(
        `🌐 **AI 서버에 연결하지 못했습니다 (Failed to fetch)**\n\n` +
          `원인 1순위: 브라우저 CORS 차단 — 현재 요청 주소: \`${AI_BASE_URL}/chat/completions\`\n` +
          `해결: \`npm run dev\`로 실행 중이면 dev 서버를 재시작하세요 (vite 프록시 \`/api/ai\` 적용됨). \`VITE_AI_BASE_URL\`을 \`https://ollama.com/v1\`로 직접 지정했다면 지우거나 \`/api/ai\`로 바꾸세요.\n\n` +
          `그 외 확인: ① \`.env\`의 \`VITE_NVIDIA_API_KEY\` 설정 후 dev 서버 재시작 ② 인터넷/VPN/광고차단 확장 확인 ③ F12 콘솔의 CORS 문구 확인 (원본: ${raw})`
      );
    }
    throw e instanceof Error ? e : new Error(String(e));
  } finally {
    clearTimeout(timer);
  }
}
