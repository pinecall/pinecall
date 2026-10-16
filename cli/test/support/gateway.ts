/** The gateway every test talks to: msw answering at one URL over real fetch, each request kept as it was sent. */

import { http, HttpResponse } from "msw/http";
import { setupServer } from "msw/node";

/** Where the fake gateway answers; a test project's `PINECALL_URL`. */
export const GATEWAY = "https://gateway.test";

/** A person's key: it opens both envs, and the `pinecall-env` header says which. */
export const KEY = "pc_live_0123456789abcdef0123456789abcdef";

/** The one server of the suite; `test/support/setup.ts` starts it, resets it after each test and refuses any request no test answered. */
export const server = setupServer();

/** One request as the CLI sent it. */
export interface Sent {
  method: string;
  path: string;
  query: Record<string, string>;
  /** The JSON body parsed; the raw bytes' length for anything else; undefined when there was none. */
  body: unknown;
  /** The `pinecall-env` header: which env the request acts in. */
  env: string | null;
  authorization: string | null;
  /** The request's `content-type`. */
  type: string | null;
}

export type Method = "get" | "post" | "put" | "patch" | "delete";

/**
 * Answer one route with JSON (`null` answers an empty 204), or with what a function of the request
 * answers, and keep every request it took, in order. The path is msw's: `/v1/agents/:slug/settings`.
 * Answers until the test ends.
 */
export function answer(method: Method, path: string, reply: (sent: Sent) => unknown): Sent[];
export function answer(method: Method, path: string, reply?: unknown): Sent[];
export function answer(method: Method, path: string, reply: unknown = null): Sent[] {
  const seen: Sent[] = [];
  server.use(
    http[method](`${GATEWAY}${path}`, async ({ request }) => {
      const sent = await sentOf(request);
      seen.push(sent);
      const body = typeof reply === "function" ? (reply as (sent: Sent) => unknown)(sent) : reply;
      return body === null || body === undefined ? new HttpResponse(null, { status: 204 }) : HttpResponse.json(body as never);
    }),
  );
  return seen;
}

/**
 * Answer one route as a server-sent stream: each frame's data as one `data:` line, then the stream
 * held open until the client lets go — a feed, a log tailed live. Every opening is kept.
 */
export function stream(path: string, frames: readonly unknown[] = []): Sent[] {
  const seen: Sent[] = [];
  server.use(
    http.get(`${GATEWAY}${path}`, async ({ request }) => {
      seen.push(await sentOf(request));
      const encoder = new TextEncoder();
      // The gateway answers a stream at once and the client counts it open then; msw hands the
      // response over at its first bytes, so a comment opens it. The body then ends, as a stream
      // the server closes: a reader that aborts a body msw still holds open makes msw complete a
      // request undici already let go (undici asserts, and the run fails on the unhandled error).
      // A reader that wants more reconnects, as it would after any drop.
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(": open\n\n"));
          frames.forEach((frame, at) => controller.enqueue(encoder.encode(`id: ${at + 1}\ndata: ${JSON.stringify(frame)}\n\n`)));
          controller.close();
        },
      });
      return new HttpResponse(body, { headers: { "content-type": "text/event-stream" } });
    }),
  );
  return seen;
}

/** Refuse one route as FastAPI does: the status and `{detail}`. */
export function refuse(method: Method, path: string, status: number, detail: string): Sent[] {
  const seen: Sent[] = [];
  server.use(
    http[method](`${GATEWAY}${path}`, async ({ request }) => {
      seen.push(await sentOf(request));
      return HttpResponse.json({ detail }, { status });
    }),
  );
  return seen;
}

async function sentOf(request: Request): Promise<Sent> {
  const url = new URL(request.url);
  const text = request.method === "GET" || request.method === "HEAD" ? "" : await request.clone().text();
  const json = (request.headers.get("content-type") ?? "").includes("application/json");
  return {
    method: request.method,
    path: url.pathname,
    query: Object.fromEntries(url.searchParams),
    body: text === "" ? undefined : json ? (JSON.parse(text) as unknown) : text.length,
    env: request.headers.get("pinecall-env"),
    authorization: request.headers.get("authorization"),
    type: request.headers.get("content-type"),
  };
}
