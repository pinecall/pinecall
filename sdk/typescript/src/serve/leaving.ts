/** How a served process leaves: asked to (a signal, its stdin's end, a stop), then a drain. */

import type { Drained, Pinecall } from "../client/index.js";
import type { Io } from "./io.js";

/** Why the process is leaving. A stop from the org is not drained: the gateway already let go. */
export type Asked = "signalled" | "ended" | "stopped";

const SIGNALS = ["SIGINT", "SIGTERM"] as const;

/** Resolve with the first reason to leave; a stop is said on `err` in the gateway's words. */
export function askedToLeave(pc: Pinecall, io: Io): Promise<Asked> {
  return new Promise((done) => {
    const signalled = (): void => leave("signalled");
    const ended = (): void => leave("ended");
    const unstop = pc.onStopped((why) => {
      io.err.write(`${why}\n`);
      leave("stopped");
    });
    for (const signal of SIGNALS) io.signals.on(signal, signalled);
    io.input.on("end", ended);
    io.input.resume();
    function leave(why: Asked): void {
      for (const signal of SIGNALS) io.signals.off(signal, signalled);
      io.input.off("end", ended);
      io.input.pause();
      unstop();
      done(why);
    }
  });
}

/** Drain every agent, unless a second signal says to leave now: then nothing. */
export async function drainedUnlessSignalledAgain(pc: Pinecall, io: Io): Promise<Drained | undefined> {
  let heard: (() => void) | undefined;
  const again = new Promise<undefined>((done) => {
    heard = () => done(undefined);
    for (const signal of SIGNALS) io.signals.on(signal, heard);
  });
  try {
    return await Promise.race([pc.drain(), again]);
  } finally {
    for (const signal of SIGNALS) io.signals.off(signal, heard!);
  }
}

/** Summarize a drain: live calls handed over or kept, tools finished or cut. */
export function drainLine(done: Drained): string {
  const calls = done.handed + done.parked;
  if (calls === 0 && done.tools === 0) return "draining · no live calls";
  const parts = ["draining"];
  if (done.handed > 0) parts.push(`${plural(done.handed, "live call")} handed over`);
  if (done.parked > 0) parts.push(`${plural(done.parked, "live call")} kept for the next process`);
  if (done.finished > 0) parts.push(`${plural(done.finished, "tool")} finished`);
  if (done.tools > done.finished) parts.push(`${plural(done.tools - done.finished, "tool")} cut`);
  return parts.join(" · ");
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}
