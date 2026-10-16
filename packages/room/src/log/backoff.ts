/** How a gateway that is away is asked again: half a second, doubling to eight, for as long as it takes. */

// A dropped stream is opened again after this, doubling to the ceiling: a gateway restarting is
// seconds, and a page hammering it every 100 ms would only make those seconds longer. A 5xx is the
// same thing seen from a proxy — the gateway behind it is restarting — and is asked again too.
const FIRST_MS = 500;
const CEILING_MS = 8_000;

/** From here up the gateway, or the proxy in front of it, is away rather than saying no. */
export const AWAY = 500;

/** One asker's pause between tries. `reset` once the gateway has answered. */
export class Backoff {
  #ms = FIRST_MS;

  /** Sleeps the current pause, cut short by `signal`, and doubles the next one. */
  async wait(signal: AbortSignal): Promise<void> {
    await slept(this.#ms, signal);
    this.#ms = Math.min(this.#ms * 2, CEILING_MS);
  }

  reset(): void {
    this.#ms = FIRST_MS;
  }
}

function slept(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((wake) => {
    const timer = setTimeout(wake, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        wake();
      },
      { once: true },
    );
  });
}
