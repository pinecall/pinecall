/** Gateway client: base URL, key, error type and 401 hook. */

// A page holds only a person's scoped key minted at login, never the org's key.
/** Gateway location and the key sent with each request. */
export interface Credentials {
  /** Gateway base as configured at boot (see gatewayUrl). */
  base: string;
  key: string;
  /** Member id whose sandbox corner an admin is viewing. */
  corner?: string | null;
  /**
   * Sent as an assertion the instance checks, not a selector: it refuses the other world's name,
   * and production refuses a person's request that names none.
   */
  world?: "production" | "sandbox";
}

/** Non-2xx gateway response; `message` is the gateway's `detail`. */
export class GatewayError extends Error {
  override readonly name = "GatewayError";

  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Message to show for a failure; `String(error)` would prefix the class name. */
export function saidBy(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}

// With no key, omit `authorization` entirely: an empty one reads as an invalid key.
/** Headers for every gateway request: Bearer key, world and corner. */
export function headersFor(credentials: Credentials): Record<string, string> {
  const headers: Record<string, string> = credentials.key === "" ? {} : { authorization: `Bearer ${credentials.key}` };
  if (credentials.world !== undefined) headers["pinecall-env"] = credentials.world;
  if (credentials.corner) headers["pinecall-corner"] = credentials.corner;
  return headers;
}

// A 401 means the key died (revoked, or a dev gateway restarted); the boot's listener decides what to do.
let unauthorized: (() => void) | null = null;

/** Set the 401 handler (installed once at boot). */
export function onUnauthorized(listener: () => void): void {
  unauthorized = listener;
}

/** GET JSON; the caller parses it with the wire's schema. */
export async function read(credentials: Credentials, path: string, params: Params = {}): Promise<unknown> {
  const answer = await fetch(doorAt(credentials, path, params), { headers: headersFor(credentials) });
  return answered(answer);
}

/** PUT JSON; the caller parses the response with the wire's schema. */
export async function put(credentials: Credentials, path: string, body: unknown): Promise<unknown> {
  const answer = await fetch(doorAt(credentials, path, {}), {
    method: "PUT",
    headers: { ...headersFor(credentials), "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return answered(answer);
}

/** PATCH JSON: only the fields sent are written; the caller parses the response with the wire's schema. */
export async function patch(credentials: Credentials, path: string, body: unknown): Promise<unknown> {
  const answer = await fetch(doorAt(credentials, path, {}), {
    method: "PATCH",
    headers: { ...headersFor(credentials), "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return answered(answer);
}

/** POST JSON; the caller parses the response with the wire's schema. */
export async function post(credentials: Credentials, path: string, body: unknown): Promise<unknown> {
  const answer = await fetch(doorAt(credentials, path, {}), {
    method: "POST",
    headers: { ...headersFor(credentials), "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return answered(answer);
}

/** DELETE, with an optional JSON body. A 204 returns null. */
export async function drop(credentials: Credentials, path: string, body?: unknown): Promise<unknown> {
  const named = body === undefined ? {} : { headers: { ...headersFor(credentials), "content-type": "application/json" }, body: JSON.stringify(body) };
  return answered(await fetch(doorAt(credentials, path, {}), { method: "DELETE", headers: headersFor(credentials), ...named }));
}

/** Full URL for callers that fetch it themselves (SSE, recordings). */
export function doorUrl(credentials: Credentials, path: string, params: Params = {}): string {
  return doorAt(credentials, path, params).toString();
}

/** A query's values; a list repeats its name, once per value (`?agent=a&agent=b`). */
type Params = Record<string, string | number | readonly string[]>;

const NO_BODY = 204;
const UNAUTHORIZED = 401;

/** Return the parsed body or throw GatewayError; a 401 also calls the handler. */
export async function answered(answer: Response): Promise<unknown> {
  if (answer.ok) {
    return answer.status === NO_BODY ? null : answer.json();
  }
  if (answer.status === UNAUTHORIZED) unauthorized?.();
  throw new GatewayError(answer.status, await detail(answer));
}

// `base` is set once at boot: "/" for the console (resolved against the page origin), the box's
// full URL for the mobile app.
/** Build a gateway URL; every gateway URL goes through here. */
export function gatewayUrl(base: string, path: string): URL {
  return new URL(base.replace(/\/$/, "") + path, window.location.origin);
}

function doorAt(credentials: Credentials, path: string, params: Params): URL {
  const door = gatewayUrl(credentials.base, path);
  for (const [name, value] of Object.entries(params)) {
    if (Array.isArray(value)) for (const one of value as readonly string[]) door.searchParams.append(name, one);
    else door.searchParams.set(name, String(value));
  }
  return door;
}

// FastAPI's `detail`, falling back to the status text.
async function detail(answer: Response): Promise<string> {
  try {
    const body: unknown = await answer.json();
    const said = (body as { detail?: unknown }).detail;
    return typeof said === "string" ? said : answer.statusText;
  } catch {
    return answer.statusText;
  }
}
