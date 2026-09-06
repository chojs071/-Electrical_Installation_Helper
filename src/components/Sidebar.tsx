import { useRef } from "react";
import { Download, ImagePlus, LogOut, Plus, Upload, X } from "lucide-react";

import { AuthPanel } from "@/components/AuthPanel";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { REF_MAX_CHATS, SIDEBAR_HEADER_IMAGE } from "@/lib/constants";
import { exportChatToJson, importChatFromJson } from "@/lib/backup";
import type { Chat, SessionUser } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SidebarProps {
  user: SessionUser | null;
  chats: Chat[];
  currentChatId?: string;
  refSelection: string[];
  pendingImage: string | null;
  onLogin: (userId: string, password: string) => Promise<string>;
  onSignup: (userId: string, password: string) => Promise<string>;
  onLogout: () => void;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onToggleRef: (id: string) => void;
  onSetPendingImage: (dataUrl: string | null) => void;
  onImportChat: (messages: Chat["messages"], name: string) => void;
}

export function Sidebar({
  user,
  chats,
  currentChatId,
  refSelection,
  pendingImage,
  onLogin,
  onSignup,
  onLogout,
  onNewChat,
  onSelectChat,
  onToggleRef,
  onSetPendingImage,
  onImportChat,
}: SidebarProps) {
  const imageFileRef = useRef<HTMLInputElement>(null);
  const jsonFileRef = useRef<HTMLInputElement>(null);

  const currentChat = chats.find((c) => c.id === currentChatId) ?? chats[0];
  const otherChats = chats.filter((c) => c.id !== currentChat?.id);

  const handleImageFile = (file: File | undefined) => {
    if (!file) return;
    if (!/image\/(png|jpe?g|webp)/i.test(file.type)) {
      alert("지원 형식: PNG, JPG, JPEG, WEBP");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => onSetPendingImage(String(reader.result));
    reader.readAsDataURL(file);
  };

  const handleJsonFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const messages = await importChatFromJson(file);
      const name = file.name.replace(/\.[^.]+$/, "");
      onImportChat(messages, name);
    } catch (e) {
      alert(`파일 읽기 오류: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <img
        src={SIDEBAR_HEADER_IMAGE}
        alt="전기설비 도우미"
        className="w-full rounded-xl object-cover"
      />

      {/* 👤 계정 메뉴 */}
      <section>
        <h3 className="mb-2 text-sm font-bold">👤 계정 메뉴</h3>
        {user ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm font-semibold">
              👋 안녕하세요, <b>{user.displayUserId}</b>님!
            </p>
            <Button variant="secondary" onClick={onLogout}>
              <LogOut /> 로그아웃
            </Button>
          </div>
        ) : (
          <AuthPanel onLogin={onLogin} onSignup={onSignup} />
        )}
      </section>

      <Separator />

      {/* 💬 대화 목록 */}
      <section>
        <h3 className="mb-2 text-sm font-bold">💬 대화 목록</h3>
        <Button className="w-full" onClick={onNewChat}>
          <Plus /> 새 대화 시작
        </Button>
        <ul className="mt-2 flex flex-col gap-1">
          {chats.map((chat) => (
            <li key={chat.id}>
              <button
                type="button"
                onClick={() => onSelectChat(chat.id)}
                className={cn(
                  "w-full truncate rounded-md border border-transparent px-3 py-2 text-left text-sm hover:bg-accent",
                  chat.id === currentChat?.id && "border-blue-200 bg-blue-50 font-semibold text-blue-700"
                )}
                title={chat.title}
              >
                {chat.title}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* 📚 과거 대화 참고 (로그인 전용) */}
      {user && (
        <>
          <Separator />
          <section>
            <h3 className="mb-2 text-sm font-bold">📚 과거 대화 참고</h3>
            <div className="mb-2 rounded-lg border-l-4 border-emerald-400 bg-emerald-50 p-2.5 text-[0.8rem]">
              💡 체크한 과거 대화 내용을 AI가 참고하여 답변합니다.
              <br />
              (최대 {REF_MAX_CHATS}개 선택 가능, 각 대화의 최근 5개 메시지만 참고)
            </div>
            {otherChats.length === 0 ? (
              <p className="text-xs text-muted-foreground">참고할 다른 대화가 없습니다.</p>
            ) : (
              <div className="flex flex-col">
                {otherChats.map((chat) => {
                  const checked = refSelection.includes(chat.id);
                  const disabled = !checked && refSelection.length >= REF_MAX_CHATS;
                  return (
                    <label
                      key={chat.id}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1.5 text-[0.85rem] hover:bg-accent",
                        disabled && "cursor-not-allowed opacity-40"
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        disabled={disabled}
                        onCheckedChange={() => onToggleRef(chat.id)}
                      />
                      <span className="truncate">📖 {chat.title}</span>
                    </label>
                  );
                })}
              </div>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              {refSelection.length
                ? `✨ ${refSelection.length}개 대화 참고 중`
                : "참고할 대화를 선택하지 않았습니다."}
            </p>
          </section>
        </>
      )}

      <Separator />

      {/* 🖼️ 이미지 입력 */}
      <section>
        <h3 className="mb-2 text-sm font-bold">🖼️ 이미지 입력</h3>
        <div className="mb-2 rounded-lg border-l-4 border-emerald-400 bg-emerald-50 p-2.5 text-[0.8rem]">
          💡 분석하거나 참고할 이미지를 업로드하세요.
          <br />
          (지원 형식: PNG, JPG, JPEG, WEBP)
        </div>
        <input
          ref={imageFileRef}
          type="file"
          accept=".png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={(e) => {
            handleImageFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <Button variant="outline" className="w-full" onClick={() => imageFileRef.current?.click()}>
          <ImagePlus /> 이미지 파일 선택
        </Button>
        {pendingImage && (
          <div className="mt-2 flex flex-col items-center gap-1.5">
            <img src={pendingImage} alt="업로드된 이미지 미리보기" className="w-full rounded-lg border" />
            <p className="text-[0.8rem] text-green-700">
              ✅ 이미지가 성공적으로 업로드되었습니다. (메시지 입력 시 함께 분석됩니다)
            </p>
            <Button variant="secondary" size="sm" onClick={() => onSetPendingImage(null)}>
              <X /> 이미지 제거
            </Button>
          </div>
        )}
      </section>

      <Separator />

      {/* 📁 수동 백업 */}
      <section>
        <h3 className="mb-2 text-sm font-bold">📁 수동으로 대화 백업 &amp; 불러오기</h3>
        <Button
          variant="secondary"
          className="w-full"
          disabled={!currentChat || currentChat.messages.length === 0}
          onClick={() => {
            if (!currentChat) return;
            exportChatToJson(currentChat, user ? user.displayUserId : "게스트");
          }}
        >
          <Download /> 현재 대화 JSON 저장
        </Button>
        <input
          ref={jsonFileRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={(e) => {
            void handleJsonFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <Button
          variant="outline"
          className="mt-2 w-full"
          onClick={() => jsonFileRef.current?.click()}
        >
          <Upload /> JSON 대화 불러오기
        </Button>
      </section>
    </div>
  );
}
