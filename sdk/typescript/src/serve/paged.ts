/** The app's page on this machine: its built folder and the three routes the platform answers for a deployed one. */

import { existsSync, readFileSync, statSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

import { visitorCode, visitorTicket, type Answered, type VisitorDoor } from "../client/visitors.js";

/** What a page is served with here. */
export interface Paging {
  /** The built folder, as a path on this machine. */
  folder: string;
  /** The slug of the agent a visitor reaches. */
  agent: string;
  door: VisitorDoor;
  port: number;
}

/** The port the page is served on unless `PINECALL_PAGE_PORT` names another. */
export const PAGE_PORT = 4747;

const INDEX = "index.html";
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".map": "application/json",
};
const NOT_BUILT = "the page is not built yet: build it into the folder app.page names, and reload";

/** Serve the page until `close()`. Resolves once it listens; rejects when the port is taken. */
export function servePage(paging: Paging): Promise<Server> {
  const server = createServer((request, response) => {
    void answered(paging, request, response).catch((failed: unknown) => {
      said(response, { status: 502, body: JSON.stringify({ detail: failed instanceof Error ? failed.message : String(failed) }) });
    });
  });
  return new Promise((listening, refused) => {
    server.once("error", refused);
    server.listen(paging.port, "127.0.0.1", () => listening(server));
  });
}

async function answered(paging: Paging, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const { pathname } = new URL(request.url ?? "/", "http://localhost");
  // No captcha on this machine: the key is the developer's own, and nobody else reaches the port.
  if (request.method === "GET" && pathname === "/pinecall/config") return said(response, { status: 200, body: JSON.stringify({ agent: paging.agent, turnstile: null }) });
  if (request.method === "POST" && pathname === "/pinecall/token") {
    const asked = await bodyOf(request);
    const resume = typeof asked["resume"] === "string" ? asked["resume"] : undefined;
    return said(response, await visitorTicket(paging.door, paging.agent, asked["scope"] === "chat" ? "chat" : "talk", resume));
  }
  if (request.method === "POST" && pathname === "/pinecall/code") return said(response, await visitorCode(paging.door, paging.agent));
  if (request.method !== "GET") return said(response, { status: 405, body: JSON.stringify({ detail: "a page is read" }) });
  file(paging.folder, pathname, response);
}

// A path that names no file is the page itself, so its own router reads it; a file asked for by its extension is missing.
function file(folder: string, pathname: string, response: ServerResponse): void {
  const root = resolve(folder);
  const asked = normalize(join(root, decodeURIComponent(pathname)));
  const inside = asked === root || asked.startsWith(root + sep);
  const found = inside && existsSync(asked) && statSync(asked).isFile() ? asked : join(root, INDEX);
  if (!inside || (found !== asked && extname(pathname) !== "") || !existsSync(found)) {
    return said(response, { status: 404, body: JSON.stringify({ detail: existsSync(join(root, INDEX)) ? `the page has no file ${pathname}` : NOT_BUILT }) });
  }
  response.writeHead(200, { "content-type": TYPES[extname(found)] ?? "application/octet-stream", "cache-control": "no-store" });
  response.end(readFileSync(found));
}

async function bodyOf(request: IncomingMessage): Promise<Record<string, unknown>> {
  let text = "";
  for await (const chunk of request) text += String(chunk);
  try {
    const read: unknown = JSON.parse(text || "{}");
    return typeof read === "object" && read !== null ? (read as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function said(response: ServerResponse, answer: Answered): void {
  if (response.headersSent) return;
  response.writeHead(answer.status, { "content-type": "application/json", "cache-control": "no-store" });
  response.end(answer.body);
}
