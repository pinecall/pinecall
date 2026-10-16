/** Terminal input: a secret without echo, or the lines of a pipe. A key never lands in argv or the scrollback. */

import { createInterface } from "node:readline";

import type { IO } from "./io.js";

/** Reads one secret, by the name it is asked under. */
export type SecretReader = (name: string) => Promise<string>;

/**
 * How a verb reads its secrets: piped, each one takes the next line of stdin, in order; on a
 * terminal, each is asked for without echo. The pipe is read once: a second readline over the same
 * stdin finds what the first one buffered gone.
 */
export function secretReader(io: IO, input: NodeJS.ReadableStream = process.stdin): SecretReader {
  const piped = linesOf(input);
  return async (name) => (io.interactive ? await typedInSilence(`${name}: `, io, input) : await piped());
}

/** Piped stdin as one line per call, in order; a line past the last is "". */
export function linesOf(input: NodeJS.ReadableStream): () => Promise<string> {
  let lines: Promise<string[]> | undefined;
  return async () => {
    lines ??= allOf(input).then((all) => (all === "" ? [] : all.split(/\r?\n/)));
    return (await lines).shift() ?? "";
  };
}

/** The whole of piped stdin, its final newline dropped: a value of several lines, a PEM key. */
export async function allOf(input: NodeJS.ReadableStream = process.stdin): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of input) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8").replace(/\r?\n$/, "");
}

/** Read one line without echoing it: readline muted by overriding `_writeToOutput`, not raw mode. */
export async function typedInSilence(prompt: string, io: IO, input: NodeJS.ReadableStream = process.stdin): Promise<string> {
  const reading = createInterface({ input, output: io.stderr, terminal: true });
  (reading as unknown as { _writeToOutput(text: string): void })._writeToOutput = () => {};
  io.stderr.write(prompt);
  const secret = await new Promise<string>((typed) => reading.question("", typed));
  reading.close();
  io.stderr.write("\n");
  return secret;
}

/** One line typed with echo: an answer to a question, never a secret. */
export async function readLine(prompt: string, io: IO, input: NodeJS.ReadableStream = process.stdin): Promise<string> {
  const reading = createInterface({ input, output: io.stderr, terminal: io.interactive });
  const answer = await new Promise<string>((typed) => reading.question(prompt, typed));
  reading.close();
  return answer;
}
