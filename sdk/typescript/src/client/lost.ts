/** Whether an error is the gateway being out of reach, which the client redials on its own. */

// `ws` and network errors for an unreachable gateway, including a proxy answering during a restart.
const LOST = /^(Unexpected server response|WebSocket|socket hang up|connect |getaddrinfo |read ECONN|write E)/;

/** Whether the error is an unreachable gateway (the client reconnects) rather than an app's own. */
export function aLostSocket(failed: Error): boolean {
  return typeof (failed as NodeJS.ErrnoException).code === "string" || LOST.test(failed.message);
}
