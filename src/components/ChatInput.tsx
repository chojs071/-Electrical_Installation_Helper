import { useEffect, useRef, useState } from "react";
import { SendHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  disabled?: boolean;
  onSend: (prompt: string) => void;
}

export function ChatInput({ disabled, onSend }: ChatInputProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const send = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  };

  return (
    <div className="flex w-full items-end gap-2">
      <Textarea
        ref={ref}
        value={value}
        rows={1}
        placeholder="질문을 입력하세요 (이미지 첨부가능)"
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          // 한글 IME 조합 중 Enter(글자 확정)는 전송하지 않음
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
          }
        }}
        className="max-h-40 resize-none"
      />
      <Button
        size="icon"
        className="h-10 w-10 shrink-0 rounded-full"
        disabled={disabled || !value.trim()}
        onClick={send}
        aria-label="전송"
      >
        <SendHorizontal />
      </Button>
    </div>
  );
}
