/** The log folded as it arrives: the protocol's own reducer, one entry at a time, every entry kept. */

import { decodeEntry } from "../wire/codec.js";
import { type Entry } from "../wire/envelope.js";
import { apply, initialState } from "../wire/reduce.js";
import { type State } from "../wire/state.js";

import type { SseMessage } from "./sse.js";

/** What the page draws from: the call as the protocol folds it, and the entries it was folded from. */
export interface Folded {
  log: State;
  entries: Entry[];
}

/**
 * One call's log, folding. The protocol's `apply` mutates the state it is given, so what this
 * holds is a working copy: `snapshot()` is what leaves it, and nothing that left is ever changed.
 */
export class LogFold {
  #state: State = initialState();
  #entries: Entry[] = [];
  readonly #onSkipped: (why: string) => void;

  constructor(onSkipped: (why: string) => void) {
    this.#onSkipped = onSkipped;
  }

  /** The working state, for a question asked right now. Read it; never keep it or hand it out. */
  get now(): Readonly<State> {
    return this.#state;
  }

  /** Fold one message in. An entry this copy of the wire cannot read is one entry, not a broken call. */
  take(message: SseMessage): Entry | null {
    if (message.data === "") return null;
    let entry: Entry;
    try {
      entry = decodeEntry(JSON.parse(message.data));
    } catch (why) {
      const said = why instanceof Error ? why.message : String(why);
      this.#onSkipped(`${message.event ?? "a message"} at ${message.id ?? "no id"}: ${said.split("\n")[0] ?? said}`);
      return null;
    }
    this.#state = apply(this.#state, entry);
    this.#entries.push(entry);
    return entry;
  }

  /** A copy to publish: the page may keep it, compare it and hand it to React. */
  snapshot(): Folded {
    return { log: structuredClone(this.#state), entries: [...this.#entries] };
  }
}
