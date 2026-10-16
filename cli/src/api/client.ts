/** The gateway client: one URL, one key, one env header; every `/v1/` request of the CLI goes through it. */

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

  /** The raw answer, for a stream (SSE) or bytes (audio); non-2xx still throws `GatewayError`. */
  async fetch(path: string, options: RequestOptions = {}): Promise<Response> {
    const answered = await fetch(this.urlOf(path, options.query), {
      method: options.method ?? "GET",
      headers: { ...this.headers(options.body), ...options.headers },
      ...(options.body === undefined ? {} : { body: encoded(options.body) }),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
    });
    if (!answered.ok) throw new GatewayError(answered.status, detailOf(await answered.text()));
    return answered;
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
