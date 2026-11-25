import { defineConfig, mergeConfig } from "vitest/config";
import base from "./vite.config";

export default mergeConfig(
  base,
  defineConfig({
    cacheDir: "/tmp/finanse-vite-cache",
    server: {
      allowedHosts: ["dev.finanse.birek.online"],
      hmr: {
        protocol: "wss",
        host: "dev.finanse.birek.online",
        clientPort: 443,
      },
      proxy: { "/api": { target: "http://backend:8000", changeOrigin: true } },
      fs: {
        strict: true,
        deny: ["**/.env*", "**/.git/**", "**/*.{crt,pem}", "**/secrets/**"],
      },
    },
  }),
);
