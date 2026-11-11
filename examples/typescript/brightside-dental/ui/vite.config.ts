// The page's dev server, and the one thing a page needs a server for: a ticket for one call, minted with the org's key.

import { readFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

import { GatewayRefused, mint } from "@pinecall/room/server";

const AGENT = "brightside-front-desk";
const GATEWAY = process.env["PINECALL_URL"] ?? "https://cloud.pinecall.io";
// Who the page may say is calling: a patient the clinic knows by her number, or nobody it knows.
const CALLERS: Record<string, string | undefined> = { ana: "+14155550142", new: undefined };

// The key `pinecall link` wrote beside the app, unless the shell has one. It never reaches the page.
function key(): string {
  if (process.env["PINECALL_KEY"]) return process.env["PINECALL_KEY"];
  try {
    const line = readFileSync(fileURLToPath(new URL("../.env", import.meta.url)), "utf8").split("\n").find((one) => one.startsWith("PINECALL_KEY="));
    return line?.slice("PINECALL_KEY=".length).trim() ?? "";
  } catch {
    return "";
  }
}

async function token(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const answer = (status: number, body: object): void => void response.writeHead(status, { "content-type": "application/json" }).end(JSON.stringify(body));
  let text = "";
  for await (const chunk of request) text += String(chunk);
  const asked = JSON.parse(text || "{}") as { scope?: string; as?: string; resume?: string };
  if (key() === "") return answer(500, { detail: "no PINECALL_KEY: run `pinecall link` in this folder" });
  try {
    const scope = asked.scope === "talk" ? "talk" : "chat";
    answer(200, await mint(key(), { url: GATEWAY, agent: AGENT, scope, ttl_s: 600, contact: CALLERS[asked.as ?? "new"], resume: asked.resume }));
  } catch (refused) {
    answer(refused instanceof GatewayRefused ? refused.status : 502, { detail: refused instanceof Error ? refused.message : String(refused) });
  }
}

const tokens: Plugin = {
  name: "brightside-tokens",
  configureServer(server) {
    server.middlewares.use("/api/token", (request, response) => void token(request, response));
  },
};

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react(), tokens],
  server: { port: 5184, strictPort: true },
  build: { outDir: "dist", emptyOutDir: true },
});
