import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" makes assets load from any path, so a study needs no per-site config.
export default defineConfig({
  base: "./",
  plugins: [react()],
});
