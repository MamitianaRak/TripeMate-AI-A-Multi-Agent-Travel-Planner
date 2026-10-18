/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    // html2pdf (~900 kB) is a lazy chunk, only loaded when the user exports a PDF.
    chunkSizeWarningLimit: 1000,
  },
  server: {
    port: 5173,
    // In development the API runs on :8000; the proxy avoids CORS entirely.
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
