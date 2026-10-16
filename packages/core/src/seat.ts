/** Request a LiveKit seat in a live call via /listen or /supervise. */

import { z } from "zod";

import { post, type Credentials } from "./api";

/** `listen` is receive-only; `supervise` may also speak. */
export type Seating = "listen" | "supervise";

// Both doors answer this shape (runtime tokens/seating.py). The token is scoped to this call only.
const SeatSchema = z.object({
  server_url: z.string(),
  participant_token: z.string(),
  identity: z.string(),
});

/** LiveKit server URL and room token; never the tenant's key. */
export type Seat = z.infer<typeof SeatSchema>;

/** Request a seat in a call. */
export async function seatIn(credentials: Credentials, call: string, door: Seating): Promise<Seat> {
  return SeatSchema.parse(await post(credentials, `/v1/calls/${call}/${door}`, {}));
}
