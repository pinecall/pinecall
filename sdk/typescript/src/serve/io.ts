/** What the serve entry reads and writes: two streams out, its environment, its stdin, its signals. */

/** Everything a verb of the entry touches outside itself, so a test hands in its own. */
export interface Io {
  out: NodeJS.WritableStream;
  err: NodeJS.WritableStream;
  env: Record<string, string | undefined>;
  /** Its end is a reason to leave: the process that started this one is gone. */
  input: NodeJS.ReadableStream;
  /** Where SIGINT and SIGTERM are heard. */
  signals: NodeJS.EventEmitter;
}

/** The process's own. */
export function processIo(): Io {
  return { out: process.stdout, err: process.stderr, env: process.env, input: process.stdin, signals: process };
}
