import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";

import { ChatInput } from "@/components/ChatInput";
import { ChatMessage } from "@/components/ChatMessage";
import { Sidebar } from "@/components/Sidebar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { useChatStore } from "@/hooks/useChatStore";
import { isSupabaseConfigured } from "@/lib/supabase";

export default function Index() {
  const { user, ready, login, signup, logout } = useAuth();
  const store = useChatStore(ready ? user : null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentChat = store.currentChat;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentChat?.messages]);

  const displayUserId = user ? user.displayUserId : "게스트";
  const refTitles = user
    ? store.refSelection
        .map((id) => store.chats.find((c) => c.id === id))
        .filter((c): c is NonNullable<typeof c> => Boolean(c))
        .map((c) => c.title)
    : [];

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        로딩 중...
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 모바일 사이드바 토글 */}
      <Button
        variant="secondary"
        size="icon"
        className="fixed left-3 top-3 z-50 lg:hidden"
        onClick={() => setSidebarOpen((v) => !v)}
        aria-label="메뉴"
      >
        {sidebarOpen ? <X /> : <Menu />}
      </Button>

      {/* 사이드바 */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-80 shrink-0 border-r bg-white shadow-xl transition-transform lg:static lg:translate-x-0 lg:shadow-none ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar
          user={user}
          chats={store.chats}
          currentChatId={currentChat?.id}
          refSelection={store.refSelection}
          pendingImage={store.pendingImage}
          onLogin={login}
          onSignup={signup}
          onLogout={() => void logout()}
          onNewChat={() => {
            store.newChat();
            setSidebarOpen(false);
          }}
          onSelectChat={(id) => {
            store.selectChat(id);
            setSidebarOpen(false);
          }}
          onToggleRef={store.toggleRef}
          onSetPendingImage={store.setPendingImage}
          onImportChat={store.importChat}
        />
      </aside>

      {/* 메인 */}
      <main className="flex min-w-0 flex-1 flex-col items-center px-4 pt-14 lg:pt-0">
        <div className="w-full max-w-3xl">
          <h1 className="mt-4 text-center text-2xl font-extrabold">⚡ 나만의 AI 전기설비 도우미 ⚡</h1>
          <p className="mb-3 text-center text-sm text-muted-foreground">
            전기 기능사/산업기사/기사 합격을 위한 맞춤형 AI 튜터
          </p>

          {!isSupabaseConfigured && (
            <div className="mb-3 rounded-lg border-l-4 border-red-400 bg-red-50 p-3 text-sm">
              ⚠️ <code>.env</code> 파일에서 <code>VITE_SUPABASE_URL</code> 또는{" "}
              <code>VITE_SUPABASE_ANON_KEY</code>를 찾을 수 없습니다. <code>.env.example</code>을
              참고해 설정해 주세요.
            </div>
          )}

          {!user && (
            <div className="mb-3 rounded-lg border-l-4 border-amber-400 bg-amber-50 p-3 text-sm">
              🎭 <b>게스트 모드</b>로 이용 중입니다. 대화는 브라우저를 닫으면 사라집니다.
              <br />
              👉 좌측 사이드바에서 <b>회원가입</b> 후 로그인하면 대화가 영구 저장됩니다!
            </div>
          )}

          {refTitles.length > 0 && (
            <div className="mb-3 rounded-lg border-l-4 border-emerald-400 bg-emerald-50 p-2.5 text-[0.85rem]">
              📚 <b>참고 중인 과거 대화:</b> {refTitles.join(", ")}
            </div>
          )}

          <p className="mb-2 text-xs text-muted-foreground">
            📌 <b>현재 대화:</b> {currentChat?.title} | 👤 {displayUserId}
          </p>
        </div>

        {/* 메시지 목록 */}
        <div className="flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto py-2">
          {currentChat && currentChat.messages.length === 0 && (
            <div className="rounded-lg border-l-4 border-blue-400 bg-slate-100 p-4 text-sm">
              👋 <b>반갑습니다!</b> 무엇이든 물어보세요.
              <br />
              예시: <i>"접지공사 종류에 대해 알려줘"</i>
            </div>
          )}
          {currentChat?.messages.map((message, i) => <ChatMessage key={i} message={message} />)}
          {store.error && (
            <div className="flex items-start justify-between gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <span>{store.error}</span>
              <button type="button" onClick={store.dismissError} aria-label="닫기">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 입력창 */}
        <div className="w-full max-w-3xl pb-4">
          <ChatInput disabled={store.sending} onSend={store.sendMessage} />
        </div>
      </main>
    </div>
  );
}
