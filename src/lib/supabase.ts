import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(url && anonKey);

// 환경변수가 없으면 더미 값으로 생성하여 앱이 크래시되지 않게 하고,
// UI에서 isSupabaseConfigured 로 안내 배너를 표시합니다.
export const supabase = createClient(
  url || "https://placeholder.supabase.co",
  anonKey || "placeholder-anon-key"
);

// 아이디 → 이메일 변환 (원본 app.py 와 동일한 규칙)
export const userIdToEmail = (userId: string) => `${userId}@myapp.local`;
export const emailToUserId = (email?: string) => String(email ?? "").split("@")[0];
