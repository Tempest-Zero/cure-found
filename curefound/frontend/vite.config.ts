import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/ui/",
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 400,
    rollupOptions: {
      output: {
        // Split heavy/optional libs into their own chunks so the initial
        // bundle is small. Cytoscape only loads when the user reaches the
        // Explorer section; GSAP only when the Hero KG canvas mounts.
        manualChunks: {
          react: ["react", "react-dom"],
          "framer-motion": ["framer-motion"],
          cytoscape: ["cytoscape"],
          gsap: ["gsap"],
          icons: ["lucide-react"],
        },
      },
    },
  },
});
