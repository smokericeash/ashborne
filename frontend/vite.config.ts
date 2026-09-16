import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("victory-vendor")) return "chart-vendor";
          if (id.includes("d3-")) return "d3";
          if (id.includes("recharts")) return "charts";
          if (id.includes("lucide-react")) return "icons";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
