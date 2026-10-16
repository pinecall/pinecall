/** The console's build: one page, served by the gateway at its root, with every asset addressed from `/`. */

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const BOX = process.env["PINECALL_BOX"] ?? "https://cloud.pinecall.io";
// The notifier is its own service and answers only the console's own origin, so the dev server
// forwards `/notify` to it (`lib/notifier.ts` asks there in dev).
const NOTIFIER = process.env["PINECALL_NOTIFIER"] ?? "https://notify.pinecall.io";

// The page's own directory is the root — `src/index.html` is the document — and the build lands in
// this app's `dist/`, which the runtime's `scripts/console` copies into the gateway as package data.
// A build here is what a browser gets there.
export default defineConfig({
  root: "src",
  plugins: [react()],
  // Absolute assets: the gateway answers `/a/<agent>/talk` with the page, and a relative asset
  // path resolved from there would be a 404 three directories deep.
  base: "/",
  // `vite` alone: the page from this checkout, the doors from a box — production's unless
  // PINECALL_BOX names another. The page asks its own origin (`lib/base.ts`), so the dev server
  // forwards the gateway's paths, naming the box as the origin so it answers as it would its own
  // page. The build never reads this.
  server: {
    proxy: {
      "/notify": {
        target: NOTIFIER,
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/notify/, ""),
        configure: (proxy: { on: (event: "proxyReq", listener: (request: { setHeader: (name: string, value: string) => void }) => void) => void }) =>
          proxy.on("proxyReq", (request) => request.setHeader("origin", BOX)),
      },
      ...Object.fromEntries(
      ["/v1", "/.well-known"].map((path) => [
        path,
        {
          target: BOX,
          changeOrigin: true,
          configure: (proxy: { on: (event: "proxyReq", listener: (request: { setHeader: (name: string, value: string) => void }) => void) => void }) =>
            proxy.on("proxyReq", (request) => request.setHeader("origin", BOX)),
        },
      ]),
      ),
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
