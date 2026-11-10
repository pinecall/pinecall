/** The console's dev server and build: the page from this folder, the gateway's doors forwarded to a box. */

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const BOX = process.env["PINECALL_BOX"] ?? "https://cloud.pinecall.io";
// The notifier is its own service and answers only the console's own origin.
const NOTIFIER = process.env["PINECALL_NOTIFIER"] ?? "https://notify.pinecall.io";

// The page asks its own origin, so the gateway's paths are forwarded, naming the box as the origin
// so it answers as it would its own page.
const forwarded = {
  target: BOX,
  changeOrigin: true,
  configure: (proxy: { on: (event: "proxyReq", listener: (request: { setHeader: (name: string, value: string) => void }) => void) => void }) =>
    proxy.on("proxyReq", (request) => request.setHeader("origin", BOX)),
};

export default defineConfig({
  root: "src",
  plugins: [react()],
  base: "/",
  server: { port: 5190, strictPort: true, proxy: { "/v1": forwarded, "/.well-known": forwarded, "/notify": { ...forwarded, target: NOTIFIER, rewrite: (path: string) => path.replace(/^\/notify/, "") } } },
  build: { outDir: "../dist", emptyOutDir: true },
});
