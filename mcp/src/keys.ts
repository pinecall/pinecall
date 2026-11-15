/** The keys requests carry, proven at the gateway and remembered for a minute: a tool call is never one more question of who asks. */

import { createHash } from "node:crypto";

/** What proves a key: the gateway's word on who holds it, or null for one that opens nothing. */
export type Prove = (key: string) => Promise<unknown | null>;

// A key the gateway took is taken for a minute: one it revoked is refused by the gateway itself at
// the next tool call, whatever is remembered here. One it refused is refused for half of that, so a
// stranger guessing keys asks the gateway once each.
export const GOOD_FOR_MS = 60_000;
export const BAD_FOR_MS = 30_000;
// Past this many remembered, the oldest go: a flood of made-up keys never grows the process.
export const MOST_REMEMBERED = 10_000;

interface Remembered {
  good: boolean;
  until: number;
}

export class Keys {
  readonly #remembered = new Map<string, Remembered>();

  constructor(
    private readonly prove: Prove,
    private readonly clock: () => number = Date.now,
  ) {}

  /** Whether the key opens the gateway; a failure of the gateway to answer is thrown, and nothing is remembered of it. */
  async opens(key: string): Promise<boolean> {
    const print = fingerprint(key);
    const known = this.#remembered.get(print);
    if (known !== undefined && known.until > this.clock()) return known.good;
    const good = (await this.prove(key)) !== null;
    this.#remembered.delete(print);
    this.#remembered.set(print, { good, until: this.clock() + (good ? GOOD_FOR_MS : BAD_FOR_MS) });
    for (const oldest of this.#remembered.keys()) {
      if (this.#remembered.size <= MOST_REMEMBERED) break;
      this.#remembered.delete(oldest);
    }
    return good;
  }
}

/** A key as it is remembered: its sha256, never itself. */
export function fingerprint(key: string): string {
  return createHash("sha256").update(key).digest("hex");
}
