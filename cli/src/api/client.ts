/** The gateway client: one URL, one key, one env header; every `/v1/` request of the CLI goes through it, a read a busy gateway refused asked again. */

import { signed, type World } from "@pinecall/agents/client";

import { GatewayError } from "../errors.js";

/** One of an org's two environments. The SDK's `World` is the same union. */
export type Env = World;

/** A request's query: undefined values are left out. */
export type Query = Record<string, string | number | boolean | undefined>;

/** What a request sends beyond its path. */
export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-encoded; a Buffer is sent as it is. */
  body?: unknown;
  query?: Query | undefined;
  headers?: Record<string, string> | undefined;
  signal?: AbortSignal | undefined;
}

// A gateway whose database had no connection free for two seconds answers `503` and says when to
// come back (`Retry-After`): thirty simulated calls on one gateway did that to the `simulate` that
// followed them (2026-11-25), which ended on the first one with every call still on the line. A read
// that changes nothing is asked again on that word, this many times in all, each wait twice the last
// and never past the longest; then the refusal is the answer, as it was. A `503` that names no time (a
// vendor nobody keyed) is an answer already, and so is every refusal of a write: asked again, a write
// may be done twice.
const A_READ_IS_ASKED = 4;
const LONGEST_WAIT_MS = 4_000;

/** The gateway at one URL, for one key, in one env. Built once per verb by the Context. */
export class GatewayClient {
  readonly url: string;

  constructor(
    url: string,
    readonly key: string,
    readonly env: Env,
  ) {
    this.url = url.replace(/\/$/, "");
  }

  /** The parsed JSON of a 2xx answer; null for an empty body. Throws `GatewayError` otherwise. */
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const text = await (await this.fetch(path, options)).text();
    return (text === "" ? null : JSON.parse(text)) as T;
  }

  get<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
    return this.request<T>(path, { query, signal });
  }

  post<T>(path: string, body?: unknown, query?: Query): Promise<T> {
    return this.request<T>(path, { method: "POST", body, query });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "PUT", body });
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "PATCH", body });
  }

  delete<T>(path: string, query?: Query): Promise<T> {
    return this.request<T>(path, { method: "DELETE", query });
  }

  /**
   * The raw answer, for a stream (SSE) or bytes (audio); non-2xx still throws `GatewayError`. A read
   * the gateway was too busy for, and said when to ask again, is asked again a few times first.
   */
  async fetch(path: string, options: RequestOptions = {}): Promise<Response> {
    const method = options.method ?? "GET";
    for (let tries = 1; ; tries += 1) {
      const answered = await fetch(this.urlOf(path, options.query), {
        method,
        headers: { ...this.headers(options.body), ...options.headers },
        ...(options.body === undefined ? {} : { body: encoded(options.body) }),
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      });
      if (answered.ok) return answered;
      const text = await answered.text();
      const wait = method === "GET" && tries < A_READ_IS_ASKED ? comeBackAfter(answered, tries) : null;
      if (wait === null || options.signal?.aborted === true) {
        const detail = detailOf(text);
        // A body with no `detail` (a proxy's page, nothing) is not a sentence of the gateway's: the status is named.
        throw new GatewayError(answered.status, detail, detail !== text);
      }
      await new Promise((wake) => setTimeout(wake, wait));
    }
  }

  /** The full URL of a path, for a socket or a browser as much as a request. */
  urlOf(path: string, query?: Query): string {
    const url = new URL(`${this.url}${path}`);
    for (const [name, value] of Object.entries(query ?? {})) if (value !== undefined) url.searchParams.set(name, String(value));
    return url.toString();
  }

  /** The signed headers alone: `authorization` and `pinecall-env`. */
  headers(body?: unknown): Record<string, string> {
    const content = body === undefined || Buffer.isBuffer(body) ? {} : { "content-type": "application/json" };
    return { ...signed(this.key, this.env), ...content };
  }
}

/** How long to wait before a busy gateway is asked again: what it said, doubled each time; null when it named no time. */
function comeBackAfter(answered: Response, tries: number): number | null {
  const said = answered.headers.get("retry-after");
  if (answered.status !== 503 || said === null || !/^\d+$/.test(said)) return null;
  return Math.min(Number(said) * 1_000 * 2 ** (tries - 1), LONGEST_WAIT_MS);
}

function encoded(body: unknown): Uint8Array | string {
  return Buffer.isBuffer(body) ? new Uint8Array(body) : JSON.stringify(body);
}

/**
 * The message of a FastAPI error body (`detail`). A 422 list becomes `field: message` pairs; an
 * unparseable body is returned unchanged.
 */
export function detailOf(text: string): string {
  try {
    const said: unknown = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof said === "string") return said;
    if (Array.isArray(said)) return said.map(oneComplaint).join("; ");
    return text;
  } catch {
    return text;
  }
}

function oneComplaint(said: unknown): string {
  const { loc, msg } = said as { loc?: unknown[]; msg?: string };
  const where = (loc ?? []).slice(1).join(".");
  return where === "" ? (msg ?? "") : `${where}: ${msg ?? ""}`;
}

/** A path segment, escaped. */
export function seg(value: string): string {
  return encodeURIComponent(value);
}
