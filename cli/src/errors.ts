/** Every error the CLI throws, each carrying the exit code `main.ts` answers with. */

/** Exit 1: what was measured did not hold — a check failed, a golden broke, a judge answered broken. */
export class PinecallError extends Error {
  override readonly name: string = "PinecallError";

  /** The exit code of a verb that ends with this error. */
  readonly exit: number = 1;
}

/** Exit 2: the verb cannot run as typed — an argument, a missing key, a setting. */
export class UsageError extends PinecallError {
  override readonly name = "UsageError";
  override readonly exit = 2;
}

/**
 * The gateway answered outside 2xx; the message is the gateway's own `detail`. Always exit 2: a
 * refusal — a name nothing answers to (404), a state that contradicts the request (409), an input
 * its schema refuses (422), a key that may not (401, 403), a quota (429), a vendor with no key (503),
 * a bad request (400) — stopped the command from running, and measured nothing. Exit 1 is only for
 * what was measured and did not hold.
 */
export class GatewayError extends PinecallError {
  override readonly name = "GatewayError";
  override readonly exit = 2;

  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`the gateway answered ${status}: ${detail}`);
  }
}

/** Exit 130: the person stopped the verb (Ctrl-C), which is not a failure. */
export class Cancelled extends PinecallError {
  override readonly name = "Cancelled";
  override readonly exit = 130;

  constructor() {
    super("stopped");
  }
}

/** The message of any failure, without its class name: `String(error)` would prefix it. */
export function errorMessage(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}
