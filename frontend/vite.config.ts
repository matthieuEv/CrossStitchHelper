import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // L'application se met à jour toute seule : sur un appareil installé sur
      // l'écran d'accueil, personne ne pense à « recharger la page ».
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
        // Les polices sont auto-hébergées : elles font partie du précache, ce
        // qui garantit un rendu identique hors ligne.
        globPatterns: ["**/*.{js,css,html,woff2,png,svg}"],
        // Les routes applicatives sont servies par le fallback SPA du backend.
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
      // En développement, le frontend est servi par Vite et l'API par uvicorn.
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
