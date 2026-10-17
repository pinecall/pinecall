/** Where a verb writes: results on stdout, everything a person reads while waiting on stderr. */

import { Writable } from "node:stream";

/** Lines for a terminal, from data; a string is one line. */
export type Render<T> = (data: T) => string | readonly string[];

/** The real terminal's own streams, for a screen that draws itself (the setup wizard). */
export interface Terminal {
  stdout: NodeJS.WriteStream;
  stdin: NodeJS.ReadStream;
}

/** The streams and switches a verb writes with. The only module that names `process.stdout`. */
export interface IO {
  readonly stdout: Writable;
  readonly stderr: Writable;
  /** Whether stdout is a terminal: tables get headers, progress gets redrawn. */
  readonly tty: boolean;
  /** The terminal's width in columns; undefined when stdout is no terminal, and help is cut at 80. */
  readonly columns: number | undefined;
  /** Whether a person is at stdin: a secret can be asked for; piped, it is read off a line. */
  readonly interactive: boolean;
  /** `--json`: a result is one JSON object and nothing else reaches stdout. */
  json: boolean;
  /** `PINECALL_DEBUG`: `debug` lines are written. */
  readonly verbose: boolean;
  /** The terminal itself, when both stdout and stdin are one; undefined piped, in a test, under the MCP server. */
  readonly terminal: Terminal | undefined;
  /** A verb's answer: the object under `--json`, the rendered lines otherwise. */
  result<T>(data: T, render: Render<T>): void;
  /** A line of the answer written as it comes (a transcript, a log); silent under `--json`. */
  print(line: string): void;
  /** What a person reads while the verb runs: where it connected, what it is doing. */
  info(line: string): void;
  warn(line: string): void;
  debug(line: string): void;
}

/** The IO of a real process: stdout, stderr, their TTY state, the debug switch. */
export function systemIO(env: NodeJS.ProcessEnv = process.env): IO {
  return new StreamIO(process.stdout, process.stderr, {
    tty: process.stdout.isTTY === true,
    columns: process.stdout.isTTY === true ? process.stdout.columns : undefined,
    interactive: process.stdin.isTTY === true,
    verbose: env["PINECALL_DEBUG"] !== undefined,
    ...(process.stdout.isTTY === true && process.stdin.isTTY === true ? { terminal: { stdout: process.stdout, stdin: process.stdin } } : {}),
  });
}

/** An IO over any two streams: the real process, or two buffers in a test. */
export class StreamIO implements IO {
  readonly tty: boolean;
  readonly columns: number | undefined;
  readonly interactive: boolean;
  readonly verbose: boolean;
  readonly terminal: Terminal | undefined;
  json = false;

  constructor(
    readonly stdout: Writable,
    readonly stderr: Writable,
    options: { tty?: boolean; columns?: number | undefined; interactive?: boolean; verbose?: boolean; terminal?: Terminal } = {},
  ) {
    this.tty = options.tty ?? false;
    this.columns = options.columns;
    this.interactive = options.interactive ?? false;
    this.verbose = options.verbose ?? false;
    this.terminal = options.terminal;
  }

  result<T>(data: T, render: Render<T>): void {
    if (this.json) {
      this.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
      return;
    }
    const lines = render(data);
    for (const line of typeof lines === "string" ? [lines] : lines) this.stdout.write(`${line}\n`);
  }

  print(line: string): void {
    if (!this.json) this.stdout.write(`${line}\n`);
  }

  info(line: string): void {
    this.stderr.write(`${line}\n`);
  }

  warn(line: string): void {
    this.stderr.write(`warning: ${line}\n`);
  }

  debug(line: string): void {
    if (this.verbose) this.stderr.write(`debug: ${line}\n`);
  }
}

/** An IO that keeps what a verb answers, for a caller that is no terminal: the MCP server, a test. */
export class CollectingIO implements IO {
  readonly tty = false;
  readonly columns = undefined;
  readonly interactive = false;
  readonly verbose = false;
  readonly terminal = undefined;
  json = false;
  /** The results, as data: what `result` was given. */
  readonly results: unknown[] = [];
  /** Every line of `print`, `info` and `warn`, in order. */
  readonly lines: string[] = [];
  readonly stdout: Writable = new Sink();
  readonly stderr: Writable = new Sink();

  result<T>(data: T, _render: Render<T>): void {
    this.results.push(data);
  }

  print(line: string): void {
    this.lines.push(line);
  }

  info(line: string): void {
    this.lines.push(line);
  }

  warn(line: string): void {
    this.lines.push(`warning: ${line}`);
  }

  debug(_line: string): void {}
}

class Sink extends Writable {
  override _write(_chunk: unknown, _encoding: BufferEncoding, done: () => void): void {
    done();
  }
}
