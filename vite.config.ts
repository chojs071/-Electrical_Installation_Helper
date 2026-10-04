import path from "path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, loadEnv } from "vite";

function resolveUpstream(mode: string): URL {
  try {
    // prefix "" 로 VITE_ 외 변수(AI_BASE_URL)까지 읽음. 실제 셸 환경변수가 .env보다 우선.
    const env = loadEnv(mode, process.cwd(), "");
    const raw = process.env.AI_BASE_URL || env.AI_BASE_URL || "https://ollama.com/v1";
    return new URL(raw);
  } catch {
    return new URL("https://ollama.com/v1");
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const upstream = resolveUpstream(mode);
  // 끝 슬래시 제거. 경로가 없으면 "" (rewrite 시 "//" 방지)
  const basePath = upstream.pathname.replace(/\/+$/, "");
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 8080,
      // 브라우저 CORS 회피용 dev 프록시: /api/ai → upstream(AI_BASE_URL 환경변수)
      // 로컬에서 프로바이더를 바꾸려면 .env에 AI_BASE_URL만 지정하면 됨
      proxy: {
        "/api/ai": {
          target: upstream.origin,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api\/ai/, basePath),
        },
      },
    },
  };
});
