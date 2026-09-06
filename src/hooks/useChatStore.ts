import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { streamChatCompletion } from "@/lib/ai";
import {
  BASE_SYSTEM_PROMPT,
  MAX_HISTORY_MESSAGES,
  REF_MAX_CHATS,
  REF_MESSAGES_PER_CHAT,
} from "@/lib/constants";
import { loadRelevantData } from "@/lib/rag";
import { supabase } from "@/lib/supabase";
import type { Chat, ChatMessage, ImagePart, SessionUser, TextPart } from "@/lib/types";
import { uuid } from "@/lib/utils";

const GUEST_CHATS_KEY = "guest_chats";
const GUEST_CURRENT_KEY = "guest_current_chat_id";
const REF_SELECTION_KEY = "ref_selection";

function defaultChat(chatCount: number): Chat {
  return { id: uuid(), title: `새로운 대화 ${chatCount + 1}`, messages: [] };
}

/** 선택된 과거 대화들을 참고 자료 문자열로 구성 (원본 collect_reference_chats 와 동일) */
function collectReferenceChats(
  chats: Chat[],
  selectedIds: string[],
  currentChatId: string
): string {
  if (!selectedIds.length) return "";
  const refParts: string[] = [];

  for (const chatId of selectedIds) {
    if (chatId === currentChatId) continue;
    const chat = chats.find((c) => c.id === chatId);
    if (!chat) continue;

    const recent = chat.messages.slice(-REF_MESSAGES_PER_CHAT);
    if (!recent.length) continue;

    let content = `\n--- [과거 대화: ${chat.title}] ---\n`;
    for (const msg of recent) {
      const role = msg.role === "user" ? "사용자" : "AI";
      const text =
        typeof msg.content === "string"
          ? msg.content
          : msg.content
              .filter((p) => p.type === "text")
              .map((p) => (p as TextPart).text)
              .join(" ");
      content += `${role}: ${text}\n`;
    }
    refParts.push(content);
  }
  return refParts.join("\n");
}

async function saveChatToDb(userId: string, chat: Chat): Promise<void> {
  const { error } = await supabase.from("user_chats").upsert(
    {
      id: chat.id,
      user_id: userId,
      title: chat.title,
      messages: chat.messages,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "id" }
  );
  if (error) throw error;
}

export function useChatStore(user: SessionUser | null) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [refSelection, setRefSelection] = useState<string[]>([]);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatsRef = useRef<Chat[]>([]);
  chatsRef.current = chats;

  // 사용자 변경 시 대화 목록 로드 (로그인: Supabase DB / 게스트: sessionStorage)
  useEffect(() => {
    let cancelled = false;

    if (user) {
      supabase
        .from("user_chats")
        .select("*")
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false })
        .then(({ data, error: dbError }) => {
          if (cancelled) return;
          if (dbError) {
            setError(`대화 목록 불러오기 실패: ${dbError.message}`);
          }
          const loaded: Chat[] = (data ?? []).map((row) => ({
            id: String(row.id),
            title: String(row.title ?? "제목 없음"),
            messages: (row.messages as ChatMessage[]) ?? [],
          }));
          const initial: Chat[] = loaded.length ? loaded : [defaultChat(0)];
          setChats(initial);
          setCurrentChatId(initial[0].id);
        });
      try {
        const saved = JSON.parse(sessionStorage.getItem(REF_SELECTION_KEY) ?? "[]");
        if (Array.isArray(saved)) setRefSelection(saved.filter((v) => typeof v === "string"));
      } catch {
        setRefSelection([]);
      }
    } else {
      let guest: Chat[] = [];
      try {
        const saved = JSON.parse(sessionStorage.getItem(GUEST_CHATS_KEY) ?? "[]");
        if (Array.isArray(saved)) guest = saved;
      } catch {
        guest = [];
      }
      setChats(guest.length ? guest : [defaultChat(0)]);
      const cur = sessionStorage.getItem(GUEST_CURRENT_KEY);
      setCurrentChatId(cur && guest.some((c) => c.id === cur) ? cur : (guest[0]?.id ?? null));
      setRefSelection([]);
    }

    return () => {
      cancelled = true;
    };
    // user 객체 전체가 아닌 id만 추적 (토큰 갱신 등 불필요한 재조회 방지)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  // 게스트 대화는 sessionStorage 에 자동 저장 (브라우저 닫으면 사라짐)
  useEffect(() => {
    if (user) return;
    try {
      sessionStorage.setItem(GUEST_CHATS_KEY, JSON.stringify(chats));
      if (currentChatId) sessionStorage.setItem(GUEST_CURRENT_KEY, currentChatId);
    } catch {
      // 용량 초과(이미지 포함 대화 등) 시 저장만 생략 — 메모리 상태는 유지
    }
  }, [chats, currentChatId, user]);

  // 과거 대화 참고 선택 저장 (로그인 시만)
  useEffect(() => {
    if (!user) return;
    sessionStorage.setItem(REF_SELECTION_KEY, JSON.stringify(refSelection));
  }, [refSelection, user]);

  const currentChat = useMemo(
    () => chats.find((c) => c.id === currentChatId) ?? chats[0],
    [chats, currentChatId]
  );

  const newChat = useCallback(() => {
    const chat = defaultChat(chatsRef.current.length);
    setChats((prev) => [...prev, chat]);
    setCurrentChatId(chat.id);
  }, []);

  const selectChat = useCallback((id: string) => {
    setCurrentChatId(id);
  }, []);

  const importChat = useCallback((messages: ChatMessage[], name: string) => {
    const chat: Chat = { id: uuid(), title: `📂 ${name}`, messages };
    setChats((prev) => [...prev, chat]);
    setCurrentChatId(chat.id);
  }, []);

  const toggleRef = useCallback((chatId: string) => {
    setRefSelection((prev) => {
      if (prev.includes(chatId)) return prev.filter((id) => id !== chatId);
      if (prev.length >= REF_MAX_CHATS) return prev;
      return [...prev, chatId];
    });
  }, []);

  const sendMessage = useCallback(
    async (prompt: string): Promise<void> => {
      const text = prompt.trim();
      if (!text || sending) return;
      setError(null);

      const chat = currentChat;
      if (!chat) return;
      const chatId = chat.id;

      let title = chat.title;
      const baseMessages = chat.messages;
      if (baseMessages.length === 0) {
        title = text.length > 15 ? `${text.slice(0, 15)}...` : text;
      }

      // 사용자 메시지 구성 (멀티모달: 텍스트 + 선택 시 이미지)
      const parts: Array<TextPart | ImagePart> = [{ type: "text", text }];
      if (pendingImage) {
        parts.push({ type: "image_url", image_url: { url: pendingImage } });
        setPendingImage(null);
      }
      const userMessage: ChatMessage =
        parts.length === 1 ? { role: "user", content: text } : { role: "user", content: parts };
      const messages = [...baseMessages, userMessage];

      const updatedChat: Chat = { ...chat, title, messages };
      setChats((prev) => prev.map((c) => (c.id === chatId ? updatedChat : c)));

      // 사용자 메시지 먼저 저장 (원본과 동일 순서)
      if (user) {
        try {
          await saveChatToDb(user.id, updatedChat);
        } catch (e) {
          setError(`대화 저장 실패: ${e instanceof Error ? e.message : e}`);
        }
      }

      // 스트리밍용 빈 어시스턴트 메시지
      setSending(true);
      setChats((prev) =>
        prev.map((c) =>
          c.id === chatId
            ? { ...c, messages: [...messages, { role: "assistant", content: "" }] }
            : c
        )
      );

      const appendDelta = (delta: string) => {
        setChats((prev) =>
          prev.map((c) => {
            if (c.id !== chatId) return c;
            const msgs = [...c.messages];
            const last = msgs[msgs.length - 1];
            msgs[msgs.length - 1] = {
              role: "assistant",
              content: (typeof last.content === "string" ? last.content : "") + delta,
            };
            return { ...c, messages: msgs };
          })
        );
      };

      try {
        const dataContext = loadRelevantData(text);
        const refContext = user
          ? collectReferenceChats(chatsRef.current, refSelection, chatId)
          : "";

        let systemPrompt = BASE_SYSTEM_PROMPT;
        if (dataContext) systemPrompt += `\n\n[참고 자료]\n${dataContext}`;
        if (refContext) systemPrompt += `\n\n[과거 대화 참고 자료]\n${refContext}`;

        const full = await streamChatCompletion({
          systemPrompt,
          messages: messages.slice(-MAX_HISTORY_MESSAGES),
          onDelta: appendDelta,
        });

        // AI 응답 저장
        if (user) {
          const finalChat: Chat = {
            ...updatedChat,
            messages: [...messages, { role: "assistant", content: full }],
          };
          setChats((prev) => prev.map((c) => (c.id === chatId ? finalChat : c)));
          try {
            await saveChatToDb(user.id, finalChat);
          } catch (e) {
            setError(`대화 저장 실패: ${e instanceof Error ? e.message : e}`);
          }
        }
      } catch (e) {
        // 실패한 AI 응답은 대화에서 제거하고 오류만 표시 (원본과 동일)
        setChats((prev) =>
          prev.map((c) => (c.id === chatId ? { ...c, messages } : c))
        );
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setSending(false);
      }
    },
    [currentChat, pendingImage, refSelection, sending, user]
  );

  return {
    chats,
    currentChat,
    refSelection,
    pendingImage,
    sending,
    error,
    dismissError: () => setError(null),
    newChat,
    selectChat,
    importChat,
    toggleRef,
    setPendingImage,
    sendMessage,
  };
}
