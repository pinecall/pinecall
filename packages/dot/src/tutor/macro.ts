/** A macro's step on the page: its beats armed when the step arrives, each run as its word is said. */
//
// The agent sends a step and then says it. The page binds the step to the next reply it hears, and
// counts the reply's words as the voice says them (room's karaoke, from the log's word timings):
// a beat runs when its word starts. So the pointer is in time with the voice to the word, whatever
// the voice, and nothing has to be timed on the agent's side.

import type { Beat, Step } from "../wire/index.js";
import { normal, wordsOf } from "../wire/index.js";

/** Where each beat sits in its step: the index of the word it hangs on, or -1 when the step never says it. */
export function placesOf(step: Pick<Step, "say" | "beats">): number[] {
  const words = wordsOf(step.say);
  return step.beats.map((beat) => {
    const wanted = normal(beat.word);
    let seen = 0;
    for (let at = 0; at < words.length; at += 1) {
      if (words[at] !== wanted) continue;
      seen += 1;
      if (seen === (beat.nth ?? 1)) return at;
    }
    return -1;
  });
}

interface Armed {
  step: Step;
  places: number[];
  fired: Set<number>;
  /** The reply it was bound to; null until one starts after it arrived. */
  speech: string | null;
  /** The reply under way when it arrived, which is not its own. */
  before: string | null;
}

/** One step at a time: a new one replaces the one before, whose beats are left. */
export class Player {
  #armed: Armed | null = null;

  /** A step arrived. `speaking` is the reply under way now, if any. */
  arm(step: Step, speaking: string | null): void {
    this.#armed = { step, places: placesOf(step), fired: new Set(), speech: null, before: speaking };
  }

  get armed(): boolean {
    return this.#armed !== null;
  }

  /**
   * The beats due now, each once: `speech` is the reply being said (null when none is) and `lit`
   * the words of it said so far. A step whose reply has ended is done.
   */
  due(speech: string | null, lit: string): Beat[] {
    const armed = this.#armed;
    if (armed === null) return [];
    if (armed.speech === null) {
      if (speech === null || speech === armed.before) return [];
      armed.speech = speech;
    }
    if (speech !== armed.speech) {
      this.#armed = null;
      return [];
    }
    const said = wordsOf(lit).length;
    const due: Beat[] = [];
    armed.step.beats.forEach((beat, at) => {
      const place = armed.places[at] ?? -1;
      if (place < 0 || place >= said || armed.fired.has(at)) return;
      armed.fired.add(at);
      due.push(beat);
    });
    return due;
  }

  /** Leave the step: the visitor spoke, or the tutor stopped. */
  drop(): void {
    this.#armed = null;
  }
}
