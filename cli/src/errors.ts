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

/**
 * The gateway answered outside 2xx; the message is the gateway's own `detail`. A 404 is a name the
 * gateway has nothing for — an agent, a judge, a monitor, a run typed wrong — so exit 2, as every
 * name typed wrong is; any other refusal is exit 1.
 */
export class GatewayError extends PinecallError {
  override readonly name = "GatewayError";
  override readonly exit: number;

  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`the gateway answered ${status}: ${detail}`);
    this.exit = status === 404 ? 2 : 1;
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
