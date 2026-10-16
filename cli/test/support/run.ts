/** The CLI as a person types it: argv in; the exit code, stdout and stderr out; the gateway the fake one, stdin what the test pipes. */

import { Readable, Writable } from "node:stream";

import { main } from "../../src/main.js";
import { StreamIO } from "../../src/kit/io.js";
import { GATEWAY, KEY } from "./gateway.js";
import { folder, project } from "./project.js";

/** What one invocation left behind. */
export interface Ran {
  code: number;
  out: string;
  err: string;
}

export interface RunOptions {
  /** Where it was typed; a project of one agent, `front-desk`, when left out. */
  cwd?: string;
  /** The key the environment holds; `null` for none. */
  key?: string | null;
  /** What is piped to stdin: a secret, one line per value. */
  stdin?: string;
  /** More of the environment. */
  env?: NodeJS.ProcessEnv;
}

/** Run `pinecall <argv>` in-process against the fake gateway; stdout is not a terminal. */
export async function run(argv: readonly string[], options: RunOptions = {}): Promise<Ran> {
  const out = new Text();
  const err = new Text();
  const key = options.key === undefined ? KEY : options.key;
  const processEnv: NodeJS.ProcessEnv = { PINECALL_URL: GATEWAY, PINECALL_HOME: folder(), ...(key === null ? {} : { PINECALL_KEY: key }), ...options.env };
  const code = await withStdin(options.stdin ?? "", () => main(argv, new StreamIO(out, err), processEnv, options.cwd ?? project()));
  return { code, out: out.text, err: err.text };
}

/** `run` answering the JSON a verb prints under `--json`. */
export async function runJson<T = unknown>(argv: readonly string[], options: RunOptions = {}): Promise<T> {
  const ran = await run(["--json", ...argv], options);
  if (ran.code !== 0) throw new Error(`exit ${ran.code}: ${ran.err}`);
  return JSON.parse(ran.out) as T;
}

// The verbs read their secrets off process.stdin: it is swapped for the test's text while the verb runs.
async function withStdin<T>(text: string, act: () => Promise<T>): Promise<T> {
  const real = Object.getOwnPropertyDescriptor(process, "stdin")!;
  Object.defineProperty(process, "stdin", { value: Object.assign(Readable.from(text === "" ? [] : [text]), { isTTY: false }), configurable: true });
  try {
    return await act();
  } finally {
    Object.defineProperty(process, "stdin", real);
  }
}

class Text extends Writable {
  text = "";

  override _write(chunk: unknown, _encoding: BufferEncoding, done: () => void): void {
    this.text += String(chunk);
    done();
  }
}
