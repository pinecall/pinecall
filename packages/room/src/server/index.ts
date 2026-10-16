/** @pinecall/room/server: what a tenant's server does with its key — a ticket for a seat, a call placed, a code to call with. */
//
// The key never reaches a page. The page asks the tenant's own server, the server asks the gateway
// with the key, and what comes back to the page is a ticket for one call. Nothing here is imported
// by the browser side, and nothing here needs more than `fetch`.

/** What `POST /v1/tokens` answers: where the room is, the ticket into it, the call's id, and the
 * token the page reads that call's log and recording with. The protocol's `Minted`, in rest.json. */
export interface Minted {
  server_url: string;
  participant_token: string;
  call: string;
  log_token: string;
  /** What the page keeps to resume this conversation later, as `resume`. A gateway before 0.1.49 sends none. */
  resume_token?: string | undefined;
}

/** What `POST /v1/codes` answers: the four digits a page shows beside the agent's number, when
 * they stop being a code (seconds since the epoch), and the token the page asks about them with.
 * The protocol's `Code`, in rest.json. */
export interface Code {
  code: string;
  number: string;
  expires_at: number;
  code_token: string;
}

/** What `POST /v1/agents/{agent}/dial` answers: the call's id, before anything has rung. */
export interface Dialed {
  call: string;
  agent: string;
  to: string;
  from: string;
  env: string;
  log_token: string;
}

/** What the page's log token reads the call through: the public projection, or the tenant's own —
 * the tools, the latency, the cost — when the page draws them. */
export type LogProjection = "public" | "tenant";

export interface MintOptions {
  /** The gateway, `https://cloud.pinecall.io` or your own. */
  url: string;
  agent: string;
  scope: "talk" | "chat";
  /** How long the ticket lives. The gateway's default is 60 s, and 600 s the most. */
  ttl_s?: number | undefined;
  /** Who is calling: memory files the call under it. */
  contact?: string | undefined;
  metadata?: Record<string, unknown> | undefined;
  log?: LogProjection | undefined;
  /** A `resume_token` the page kept: back into that call while it waits for the visitor, else a new
   * call that carries it on. `agent` may then be the call's own or left empty. */
  resume?: string | undefined;
  fetch?: typeof fetch | undefined;
}

export interface DialOptions {
  url: string;
  agent: string;
  /** The number to call, E.164. */
  to: string;
  /** Which of the agent's own numbers the far end sees. Unsaid, the first one it answers at. */
  from?: string | undefined;
  log?: LogProjection | undefined;
  fetch?: typeof fetch | undefined;
}

export interface ExpectOptions {
  url: string;
  agent: string;
  /** How long the code lives. The gateway's default is 600 s: 60 s the least, 1800 s the most. */
  ttl_s?: number | undefined;
  /** What the log token the page is handed once a call claims the code reads it through. */
  log?: LogProjection | undefined;
  fetch?: typeof fetch | undefined;
}

/** The gateway said no. `detail` is its own sentence when it sent one; it names the fix. */
export class GatewayRefused extends Error {
  override readonly name = "GatewayRefused";
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, detail: string | null) {
    super(detail ?? `the gateway answered ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// A gateway that has not answered in this long is not going to, and a visitor is waiting on it.
const TIMEOUT_MS = 10_000;

/** A ticket for one seat in one new call. The key needs the `talk` scope. */
export async function mint(key: string, options: MintOptions): Promise<Minted> {
  const { url, agent, scope, ttl_s, contact, metadata, log, resume } = options;
  const said = { agent: agent || undefined, scope, ttl_s, contact, metadata, log, resume };
  const body = await post(key, `${bare(url)}/v1/tokens`, said, options.fetch);
  if (!isMinted(body)) throw new Error("the gateway answered /v1/tokens with a shape this package does not know");
  return body;
}

/** Have the agent call `to`. The key needs the `talk` scope; the number must have reached the org before. */
export async function dial(key: string, options: DialOptions): Promise<Dialed> {
  const { url, agent, to, from, log } = options;
  const path = `${bare(url)}/v1/agents/${encodeURIComponent(agent)}/dial`;
  const body = await post(key, path, { to, from, log }, options.fetch);
  if (!isDialed(body)) throw new Error("the gateway answered the dial with a shape this package does not know");
  return body;
}

/** A code for a page to show beside the agent's number, for the visitor to key when they call it.
 * The key needs the `talk` scope; the agent must answer at a phone number in the key's world. */
export async function expect(key: string, options: ExpectOptions): Promise<Code> {
  const { url, agent, ttl_s, log } = options;
  const body = await post(key, `${bare(url)}/v1/codes`, { agent, ttl_s, log }, options.fetch);
  if (!isCode(body)) throw new Error("the gateway answered /v1/codes with a shape this package does not know");
  return body;
}

async function post(key: string, url: string, body: object, fetcher: typeof fetch = fetch): Promise<unknown> {
  const answer = await fetcher(url, {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const text = await answer.text();
  if (!answer.ok) throw new GatewayRefused(answer.status, detailOf(text));
  return JSON.parse(text);
}

/** FastAPI's `{"detail": "…"}`, when the body is that. A 422's list of problems is not a sentence. */
function detailOf(text: string): string | null {
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return null;
  }
  return typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
    ? body.detail
    : null;
}

function bare(url: string): string {
  return url.replace(/\/+$/, "");
}

function isMinted(body: unknown): body is Minted {
  return hasStrings(body, ["server_url", "participant_token", "call", "log_token"]);
}

function isDialed(body: unknown): body is Dialed {
  return hasStrings(body, ["call", "agent", "to", "from", "env", "log_token"]);
}

function isCode(body: unknown): body is Code {
  if (!hasStrings(body, ["code", "number", "code_token"]) || typeof body !== "object" || body === null) return false;
  return typeof Reflect.get(body, "expires_at") === "number";
}

function hasStrings(body: unknown, fields: string[]): boolean {
  return typeof body === "object" && body !== null && fields.every((field) => typeof Reflect.get(body, field) === "string");
}
