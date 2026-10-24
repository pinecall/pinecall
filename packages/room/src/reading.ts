/** Where a call is read — the tenant's relay when it gave one, the gateway with the call's own token otherwise — and where its hang-up is said. */

import type { Minted } from "./server/index.js";
import type { RoomOptions } from "./surface.js";

const GATEWAY = "https://cloud.pinecall.io";

/** The gateway the page asks, with no slash at the end. */
export function gatewayOf(options: Pick<RoomOptions, "gateway">): string {
  return (options.gateway ?? GATEWAY).replace(/\/+$/, "");
}

/** The call's log and its recording. None when neither a relay nor a token is there to read it with. */
export function readingOf(
  options: Pick<RoomOptions, "gateway" | "log">,
  call: string,
  token: string | undefined,
  minted?: Minted,
): { log: string; recording: string } | null {
  if (options.log !== undefined) {
    return { log: minted === undefined ? options.log(call) : options.log(call, minted), recording: "" };
  }
  if (typeof token !== "string" || token === "") return null;
  const at = `${gatewayOf(options)}/v1/calls/${encodeURIComponent(call)}`;
  const ticket = `?token=${encodeURIComponent(token)}`;
  return { log: `${at}/events${ticket}`, recording: `${at}/recording${ticket}` };
}

/**
 * The hang-up said at the gateway's door, with the call's own token, before the seat leaves the
 * room: a seat that publishes its hang-up on the room's data channel and leaves the same instant
 * loses it with the room, and the call waits minutes for a visitor who is not coming back. Over
 * HTTP with `keepalive`, so a tab closing on the way out still completes it. Never awaited: the
 * answer changes nothing on the page.
 */
export function hangingUp(options: Pick<RoomOptions, "gateway" | "fetch">, call: string, token: string): () => void {
  const door = `${gatewayOf(options)}/v1/calls/${encodeURIComponent(call)}/hangup?token=${encodeURIComponent(token)}`;
  const fetcher = options.fetch ?? fetch;
  return () => void fetcher(door, { method: "POST", keepalive: true }).catch(() => undefined);
}
