import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
    plugins: [react()],
    // In production, assets are served by WhiteNoise under /static/frontend/
    base: process.env.NODE_ENV === "production" ? "/static/frontend/" : "/",
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
                timeout: 600000,
                proxyTimeout: 600000
            },
            "/media": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true
            }
        }
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./src/test/setup.ts"],
    },
});
