import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/studio/",
  plugins: [react()],
  build: {
    outDir: "static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/studio/sources": "http://127.0.0.1:8765",
      "/studio/jobs": "http://127.0.0.1:8765",
      "/studio/search": "http://127.0.0.1:8765",
      "/studio/stats": "http://127.0.0.1:8765",
      "/studio/knowledge": "http://127.0.0.1:8765",
      "/studio/snapshots": "http://127.0.0.1:8765",
      "/studio/chat": "http://127.0.0.1:8765",
      "/studio/conversations": "http://127.0.0.1:8765",
      "/status": "http://0.0.0.1:8765"
    }
  }
});
