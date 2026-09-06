import path from "path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 8080,
    // 브라우저 CORS 회피용 dev 프록시: /api/ai → https://ollama.com/v1
    // .env에 VITE_AI_BASE_URL=/api/ai 로 설정하거나, 미설정 시 dev 기본값으로 사용
    proxy: {
      "/api/ai": {
        target: "https://ollama.com",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/ai/, "/v1"),
      },
    },
  },
});
