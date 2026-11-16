/** Where a verb writes: results on stdout, everything a person reads while waiting on stderr. */

import { Writable } from "node:stream";

import { paintLine } from "./paint.js";

/** Lines for a terminal, from data; a string is one line. */
export type Render<T> = (data: T) => string | readonly string[];

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
  /** Whether what is written is coloured: each stream a terminal, and no `NO_COLOR`. */
  readonly color?: { out: boolean; err: boolean };
  /** A verb's answer: the object under `--json`, the rendered lines otherwise. */
  result<T>(data: T, render: Render<T>): void;
  /** A line of the answer written as it comes (a transcript, a log); silent under `--json`. */
  print(line: string): void;
  /** A line written from the row's start, over the prompt a person is typing at: a turn landing mid-typing. */
  over(line: string): void;
  /** A text written whole as it came, its lines painted: the help. */
  page(text: string): void;
  /** The verb is over: on a terminal, what it wrote is closed with an empty line. */
  end(): void;
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
    // https://no-color.org: any value of NO_COLOR, even empty, turns colour off.
    color: { out: process.stdout.isTTY === true && env["NO_COLOR"] === undefined, err: process.stderr.isTTY === true && env["NO_COLOR"] === undefined },
  });
}

/** An IO over any two streams: the real process, or two buffers in a test. */
export class StreamIO implements IO {
  readonly tty: boolean;
  readonly columns: number | undefined;
  readonly interactive: boolean;
  readonly verbose: boolean;
  readonly color: { out: boolean; err: boolean };
  json = false;
  // On a terminal an answer stands apart from the prompts around it: an empty line before its first
  // line and one after its last. Written to stdout, the terminal itself, whichever stream spoke first.
  #aired = false;

  constructor(
    readonly stdout: Writable,
    readonly stderr: Writable,
    options: { tty?: boolean; columns?: number | undefined; interactive?: boolean; verbose?: boolean; color?: { out: boolean; err: boolean } } = {},
  ) {
    this.tty = options.tty ?? false;
    this.columns = options.columns;
    this.interactive = options.interactive ?? false;
    this.verbose = options.verbose ?? false;
    this.color = options.color ?? { out: false, err: false };
  }

  result<T>(data: T, render: Render<T>): void {
    if (this.json) {
      this.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
      return;
    }
    const rendered = render(data);
    const lines = typeof rendered === "string" ? rendered.split("\n") : rendered.flatMap((line) => line.split("\n"));
    this.air();
    for (const line of this.tty ? apart(lines) : lines) this.stdout.write(`${this.paint(line, this.color.out)}\n`);
  }

  print(line: string): void {
    if (this.json) return;
    this.air();
    this.stdout.write(`${this.paint(line, this.color.out)}\n`);
  }

  // It takes the prompt's own row, so no empty line goes before it; the verb's end still closes what it wrote.
  over(line: string): void {
    if (this.json) return;
    this.#aired ||= this.tty;
    this.stdout.write(`\r${this.paint(line, this.color.out)}\n`);
  }

  page(text: string): void {
    this.air();
    this.stdout.write(this.paint(text, this.color.out));
  }

  info(line: string): void {
    this.air();
    this.stderr.write(`${this.paint(line, this.color.err)}\n`);
  }

  end(): void {
    if (this.#aired) this.stdout.write("\n");
    this.#aired = false;
  }

  private air(): void {
    if (!this.tty || this.json || this.#aired) return;
    this.#aired = true;
    this.stdout.write("\n");
  }

  private paint(text: string, on: boolean): string {
    return on ? text.split("\n").map(paintLine).join("\n") : text;
  }

  warn(line: string): void {
    this.stderr.write(`warning: ${line}\n`);
  }

  debug(line: string): void {
    if (this.verbose) this.stderr.write(`debug: ${line}\n`);
  }
}

// On a terminal the next steps (`  → …`) stand apart from the answer they follow: an empty line before the first.
function apart(lines: readonly string[]): string[] {
  const first = lines.findIndex((line) => /^ {2,}→ /.test(line));
  if (first <= 0 || lines[first - 1] === "") return [...lines];
  return [...lines.slice(0, first), "", ...lines.slice(first)];
}

/** An IO that keeps what a verb answers, for a caller that is no terminal: the MCP server, a test. */
export class CollectingIO implements IO {
  readonly tty = false;
  readonly columns = undefined;
  readonly interactive = false;
  readonly verbose = false;
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

  over(line: string): void {
    this.lines.push(line);
  }

  page(text: string): void {
    this.lines.push(text);
  }

  info(line: string): void {
    this.lines.push(line);
  }

  end(): void {}

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
