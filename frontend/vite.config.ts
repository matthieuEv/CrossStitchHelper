import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // The application updates itself: on a device where it is installed on
      // the home screen, nobody thinks of "reloading the page".
      registerType: "autoUpdate",
      includeAssets: ["icons/apple-touch-icon.png"],
      manifest: {
        name: "CrossStitchHelper",
        short_name: "CrossStitch",
        description:
          "Suivi de grilles de point de croix, auto-hébergé et hors-ligne.",
        lang: "fr",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "any",
        background_color: "#f5ead8",
        theme_color: "#f5ead8",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "icons/icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // Fonts are self-hosted: they are part of the precache, which
        // guarantees identical rendering offline.
        globPatterns: ["**/*.{js,css,html,woff2,png,svg}"],
        // Application routes are served by the backend's SPA fallback.
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      // In development, the frontend is served by Vite and the API by uvicorn.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
