/** What the server keeps for each key between its requests — the written calls open, the runs in flight — let go once idle. */

import { HostedSession } from "pinecall/hosted";

import { fingerprint } from "./keys.js";

// A written call nobody continued for this long is hung up: the gateway would end it by its own clock too.
export const IDLE_MS = 30 * 60_000;

interface Kept {
  session: HostedSession;
  used: number;
}

export class Sessions {
  readonly #kept = new Map<string, Kept>();

  constructor(
    private readonly gateway: string,
    private readonly clock: () => number = Date.now,
  ) {}

  /** The key's session, made on its first request. */
  of(key: string): HostedSession {
    const print = fingerprint(key);
    const kept = this.#kept.get(print) ?? { session: new HostedSession(this.gateway, key), used: 0 };
    kept.used = this.clock();
    this.#kept.set(print, kept);
    return kept.session;
  }

  get size(): number {
    return this.#kept.size;
  }

  /** Let go of every session idle past `IDLE_MS`: its calls hung up, nothing kept of it. */
  async sweep(): Promise<void> {
    const idle = [...this.#kept].filter(([, kept]) => this.clock() - kept.used >= IDLE_MS);
    for (const [print] of idle) this.#kept.delete(print);
    await Promise.allSettled(idle.map(([, kept]) => kept.session.close()));
  }

  /** The server is closing: every call hung up. */
  async close(): Promise<void> {
    const all = [...this.#kept.values()];
    this.#kept.clear();
    await Promise.allSettled(all.map((kept) => kept.session.close()));
  }
}
