/** Where a call is read: the tenant's relay when it gave one, the gateway with the call's own token otherwise. */

import type { Minted } from "./server/index.js";
import type { RoomOptions } from "./room.js";

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
