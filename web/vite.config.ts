import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,                              // 0.0.0.0 바인딩 (외부 호스트에서도 접근)
    port: 5173,
    allowedHosts: [
      ".trycloudflare.com",                  // 임시 터널 URL
      ".cfargotunnel.com",                   // Cloudflare named tunnel
      // 자기 도메인 추가 시 여기에:
      // "auction.yourdomain.com",
    ],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
