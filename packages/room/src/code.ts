/** A code the page shows a caller, waited on: the gateway asked with the code's token until a call claims it or it expires. */
//
// The gateway holds each ask up to 25 s and answers `waiting` when nothing happened, so the page
// asks again at once. A network that fails or a `5xx` — a gateway restarting under a deploy — is
// asked again the way the log's stream is, backing off; a `4xx` is the gateway saying no.

import { CodeStandingSchema } from "./wire/rest.js";

import { AWAY, Backoff } from "./log/backoff.js";
import type { Code } from "./server/index.js";

/** How the wait came out: the call that claimed the code, or the sentence to show instead. */
export type Claim = { kind: "claimed"; call: string; log_token: string | null } | { kind: "failed"; error: string };

const EXPIRED = "the code expired: ask for another";
const UNKNOWN = "the gateway answered the code with a shape this package does not know";

/** Ask `gateway` about `code` until a call claims it or it expires. Null when `signal` stopped it first. */
export async function claimOf(gateway: string, code: Code, fetcher: typeof fetch, signal: AbortSignal): Promise<Claim | null> {
  const url = `${gateway}/v1/codes/${encodeURIComponent(code.code)}?wait=1&token=${encodeURIComponent(code.code_token)}`;
  const backoff = new Backoff();
  while (!signal.aborted) {
    let body: unknown;
    try {
      const answer = await fetcher(url, { signal });
      if (answer.status >= AWAY) {
        await answer.body?.cancel().catch(() => undefined);
        await backoff.wait(signal);
        continue;
      }
      if (!answer.ok) return { kind: "failed", error: `the code answered ${answer.status}` };
      body = await answer.json();
    } catch {
      // The network failed, or the answer broke before it was whole: the same as a 5xx.
      if (signal.aborted) return null;
      await backoff.wait(signal);
      continue;
    }
    const standing = CodeStandingSchema.safeParse(body);
    if (!standing.success) return { kind: "failed", error: UNKNOWN };
    backoff.reset();
    const { status, call, log_token } = standing.data;
    if (status === "expired") return { kind: "failed", error: EXPIRED };
    if (status === "claimed") return call === null ? { kind: "failed", error: UNKNOWN } : { kind: "claimed", call, log_token };
  }
  return null;
}
