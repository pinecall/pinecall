/** The agent's reply while it is being said: its words as the log delivers them, and which have sounded. */
//
// A voice call delivers one agent.transcript per word, each with `start`: the second, from the
// top of the reply, at which the voice says it (the TTS measures it; the runtime passes it on).
// A word is lit when the clock reaches it, so the words on screen are the words in the ear. A
// written call's deltas are model tokens with no timing: they are lit the moment they arrive.
// The visitor's side needs nothing here: `state.log.live.user` is what the ear has heard so far.

import { type Entry } from "./wire/envelope.js";
import { AgentTranscriptSchema } from "./wire/events-call.js";

/** One delta of the reply: a word (voice) or a token (text), and when it sounds, if it does. */
export interface Word {
  text: string;
  start: number | null;
}

/** The reply in progress: its speech id and every delta so far. */
export interface Saying {
  speech: string;
  words: Word[];
}

/** A reply split where the voice is: what has sounded, and what is still to come. */
export interface Lit {
  lit: string;
  coming: string;
}

/** The reply being said now, read back from the newest entry to the last closed turn; null when nobody is mid-reply. */
export function sayingOf(entries: readonly Entry[]): Saying | null {
  const words: Word[] = [];
  let speech: string | null = null;
  for (let at = entries.length - 1; at >= 0; at -= 1) {
    const entry = entries[at];
    if (entry === undefined || entry.type === "turn.agent") break;
    if (entry.type !== "agent.transcript") continue;
    const delta = AgentTranscriptSchema.safeParse(entry.data);
    if (!delta.success) continue;
    if (delta.data.final) break;
    // Only the newest reply: a delta of an earlier speech is a reply that already closed.
    if (speech === null) speech = delta.data.speech_id;
    else if (delta.data.speech_id !== speech) break;
    words.unshift({ text: delta.data.text, start: delta.data.start ?? null });
  }
  return speech === null ? null : { speech, words };
}

/**
 * How many words have sounded `elapsed` ms after the reply's first word reached the page. A word
 * with no timing is lit at once; the count never skips a word, so a late one holds back the rest.
 */
export function soundedBy(words: readonly Word[], elapsed: number): number {
  let lit = 0;
  for (const word of words) {
    if (word.start !== null && word.start * 1000 > elapsed) break;
    lit += 1;
  }
  return lit;
}

/** The deltas as one line, the way the wire's reducer joins them: a timed word is its own word. */
export function joined(words: readonly Word[]): string {
  let line = "";
  for (const word of words) {
    if (line === "") line = word.text;
    else if (word.start !== null && !/\s$/.test(line) && !/^\s/.test(word.text)) line = `${line} ${word.text}`;
    else line = `${line}${word.text}`;
  }
  return line;
}

/** The reply split at `elapsed` ms: the words that have sounded, and the rest. */
export function litAt(saying: Saying, elapsed: number): Lit {
  const lit = joined(saying.words.slice(0, soundedBy(saying.words, elapsed)));
  return { lit, coming: joined(saying.words).slice(lit.length) };
}
