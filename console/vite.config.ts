import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the built bundle works under any path — nginx at "/",
// a subdirectory on GitHub Pages, or a preview deployment.
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173, host: true },
  build: { outDir: "dist", sourcemap: true },
});
