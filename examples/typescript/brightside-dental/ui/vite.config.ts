// The page's dev server and its build. Its tickets are asked of /pinecall/…, which `pinecall start` answers on this
// machine and Pinecall answers for the deployed app: the dev server passes them on, so the page is written once.

import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Where `pinecall start` serves the app's page and its routes (PINECALL_PAGE_PORT names another port).
const STARTED = `http://localhost:${process.env["PINECALL_PAGE_PORT"] ?? "4747"}`;

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  server: { port: 5184, strictPort: true, proxy: { "/pinecall": STARTED } },
  build: { outDir: "dist", emptyOutDir: true },
});
