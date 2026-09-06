import { useCallback, useEffect, useState } from "react";
import { emailToUserId, supabase, userIdToEmail } from "@/lib/supabase";
import type { SessionUser } from "@/lib/types";

function fromSessionUser(user: import("@supabase/supabase-js").User | undefined): SessionUser | null {
  if (!user) return null;
  return { id: user.id, displayUserId: emailToUserId(user.email) || user.id };
}

/** 원본 app.py 와 동일한 오류 메시지 매핑 */
function mapAuthError(e: Error): Error {
  const msg = e.message.toLowerCase();
  if (msg.includes("rate limit")) {
    return new Error("⚠️ 시도가 너무 많습니다. 1시간 후 다시 시도해 주세요.");
  }
  if (msg.includes("invalid login credentials")) {
    return new Error("로그인 실패: 아이디 또는 비밀번호가 올바르지 않습니다.");
  }
  if (msg.includes("user already registered")) {
    return new Error("이미 등록된 아이디입니다. 로그인 탭에서 로그인해 주세요.");
  }
  return e;
}

export function useAuth() {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    supabase.auth
      .getSession()
      .then(({ data }) => setUser(fromSessionUser(data.session?.user)))
      .finally(() => setReady(true));

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(fromSessionUser(session?.user));
    });
    return () => subscription.subscription.unsubscribe();
  }, []);

  const login = useCallback(async (userId: string, password: string): Promise<string> => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: userIdToEmail(userId),
      password,
    });
    if (error) throw mapAuthError(error);
    if (!data.user) throw new Error("로그인 실패: 아이디 또는 비밀번호가 올바르지 않습니다.");
    return "로그인 성공!";
  }, []);

  const signup = useCallback(
    async (userId: string, password: string): Promise<string> => {
      const email = userIdToEmail(userId);
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) throw mapAuthError(error);

      if (data.session && data.user) {
        return `🎉 ${userId}님, 환영합니다! 자동으로 로그인되었습니다.`;
      }
      // 이메일 확인 활성화 프로젝트는 session 이 없음 → 자동 로그인 시도 (원본 로직)
      if (data.user) {
        const login = await supabase.auth.signInWithPassword({ email, password });
        if (login.data.user) return `🎉 ${userId}님, 환영합니다!`;
      }
      return "회원가입이 완료되었습니다. 로그인해 주세요.";
    },
    []
  );

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  return { user, ready, login, signup, logout };
}
