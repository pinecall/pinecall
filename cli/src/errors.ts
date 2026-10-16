/** Every error the CLI throws, each carrying the exit code `main.ts` answers with. */

/** Exit 1: a check failed, a golden broke, something was found wrong. */
export class PinecallError extends Error {
  override readonly name: string = "PinecallError";

  /** The exit code of a verb that ends with this error. */
  readonly exit: number = 1;
}

/** Exit 2: the verb cannot run as typed — an argument, a missing key, a setting; retrying cannot help. */
export class UsageError extends PinecallError {
  override readonly name = "UsageError";
  override readonly exit = 2;
}

/** Exit 1: the gateway answered outside 2xx; the message is the gateway's own `detail`. */
export class GatewayError extends PinecallError {
  override readonly name = "GatewayError";

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
