import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AI_AVATAR_URL } from "@/lib/constants";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === "user";

  return (
    <div className="flex items-start gap-3">
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-xl",
          isUser ? "bg-muted" : "bg-background border"
        )}
      >
        {isUser ? (
          <span>👤</span>
        ) : (
          <img src={AI_AVATAR_URL} alt="AI" className="h-full w-full object-cover" />
        )}
      </div>

      <div
        className={cn(
          "max-w-[calc(100%-3rem)] rounded-xl border px-4 py-3 text-[0.95rem]",
          isUser ? "bg-blue-50 border-blue-200" : "bg-card"
        )}
      >
        {typeof message.content === "string" ? (
          message.content ? (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          ) : (
            <span className="animate-pulse text-muted-foreground">…</span>
          )
        ) : (
          <div className="flex flex-col gap-2">
            {message.content.map((part, i) =>
              part.type === "text" ? (
                <div key={i} className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.text}</ReactMarkdown>
                </div>
              ) : (
                <img
                  key={i}
                  src={part.image_url.url}
                  alt="첨부 이미지"
                  className="max-w-full rounded-lg"
                />
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}
