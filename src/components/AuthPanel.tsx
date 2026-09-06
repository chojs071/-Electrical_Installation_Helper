import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface AuthPanelProps {
  onLogin: (userId: string, password: string) => Promise<string>;
  onSignup: (userId: string, password: string) => Promise<string>;
}

export function AuthPanel({ onLogin, onSignup }: AuthPanelProps) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ type: "error" | "success"; text: string } | null>(null);

  const [loginId, setLoginId] = useState("");
  const [loginPw, setLoginPw] = useState("");
  const [signupId, setSignupId] = useState("");
  const [signupPw, setSignupPw] = useState("");
  const [signupConfirm, setSignupConfirm] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginId || !loginPw) {
      setNotice({ type: "error", text: "아이디와 비밀번호를 모두 입력해주세요." });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const message = await onLogin(loginId, loginPw);
      setNotice({ type: "success", text: message });
      setLoginId("");
      setLoginPw("");
    } catch (err) {
      setNotice({ type: "error", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!signupId || !signupPw || !signupConfirm) {
      setNotice({ type: "error", text: "모든 필드를 입력해주세요." });
      return;
    }
    if (signupId.length < 3) {
      setNotice({ type: "error", text: "아이디는 3자 이상이어야 합니다." });
      return;
    }
    if (signupPw !== signupConfirm) {
      setNotice({ type: "error", text: "비밀번호가 일치하지 않습니다." });
      return;
    }
    if (signupPw.length < 6) {
      setNotice({ type: "error", text: "비밀번호는 6자 이상이어야 합니다." });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const message = await onSignup(signupId, signupPw);
      setNotice({ type: "success", text: message });
      setSignupId("");
      setSignupPw("");
      setSignupConfirm("");
    } catch (err) {
      setNotice({ type: "error", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <Tabs defaultValue="login">
        <TabsList className="w-full">
          <TabsTrigger value="login" className="flex-1">
            🔑 로그인
          </TabsTrigger>
          <TabsTrigger value="signup" className="flex-1">
            📝 회원가입
          </TabsTrigger>
        </TabsList>

        <TabsContent value="login">
          <form onSubmit={handleLogin} className="flex flex-col gap-2">
            <Input
              placeholder="아이디를 입력하세요"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              autoComplete="username"
            />
            <Input
              type="password"
              placeholder="비밀번호를 입력하세요"
              value={loginPw}
              onChange={(e) => setLoginPw(e.target.value)}
              autoComplete="current-password"
            />
            <Button type="submit" disabled={busy}>
              {busy ? "로그인 처리 중..." : "로그인"}
            </Button>
          </form>
        </TabsContent>

        <TabsContent value="signup">
          <form onSubmit={handleSignup} className="flex flex-col gap-2">
            <Input
              placeholder="3자 이상 영문/숫자"
              value={signupId}
              onChange={(e) => setSignupId(e.target.value)}
              autoComplete="username"
            />
            <Input
              type="password"
              placeholder="6자 이상"
              value={signupPw}
              onChange={(e) => setSignupPw(e.target.value)}
              autoComplete="new-password"
            />
            <Input
              type="password"
              placeholder="다시 입력"
              value={signupConfirm}
              onChange={(e) => setSignupConfirm(e.target.value)}
              autoComplete="new-password"
            />
            <Button type="submit" disabled={busy}>
              {busy ? "회원가입 처리 중..." : "회원가입"}
            </Button>
          </form>
        </TabsContent>
      </Tabs>

      {notice && (
        <p
          className={
            notice.type === "error" ? "text-sm text-destructive" : "text-sm text-green-700"
          }
        >
          {notice.text}
        </p>
      )}

      <div className="rounded-lg border-l-4 border-amber-400 bg-amber-50 p-3 text-[0.85rem]">
        🎭 <b>게스트 모드</b>로 이용 중입니다.
        <br />
        💡 로그인하면 대화가 <b>영구 저장</b>됩니다!
      </div>
    </div>
  );
}
