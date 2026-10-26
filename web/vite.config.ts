/// <reference types="vitest/config" />
import fs from "node:fs";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server for laptops and phones on the LAN. With Tailscale Serve you normally use
// the built app served by Go instead (see docs/DEVELOPMENT_SETUP.md).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const https =
    env.DEV_HTTPS_CERT && env.DEV_HTTPS_KEY
      ? { cert: fs.readFileSync(env.DEV_HTTPS_CERT), key: fs.readFileSync(env.DEV_HTTPS_KEY) }
      : undefined;
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      https,
      proxy: {
        "/api": { target: env.DEV_API_PROXY_TARGET || "http://127.0.0.1:8080" },
      },
    },
    test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
  };
});
