/** The call's finished turns, and an optional summary that replaces older ones. */

/** One finished turn from `turn.user` or `turn.agent`. Metrics stay in the log. */
export interface Turn {
  who: "user" | "agent";
  text: string;
  /** Links a caller's turn to the reply it triggered. */
  speechId: string;
  /** True when the caller interrupted the agent; always false for user turns. */
  interrupted: boolean;
  at: number;
}

/** The call's finished turns, oldest first. A turn still being spoken is not included. */
export class History {
  readonly #turns: Turn[] = [];
  #summary: string | null = null;

  /** Every finished turn, oldest first. */
  get turns(): readonly Turn[] {
    return this.#turns;
  }

  /** Number of turns kept. */
  get length(): number {
    return this.#turns.length;
  }

  /** The summary left by `collapse()`, or null. */
  get summary(): string | null {
    return this.#summary;
  }

  /** The most recent turn. */
  get last(): Turn | undefined {
    return this.#turns[this.#turns.length - 1];
  }

  /** Append a finished turn. Called by the bridge only. */
  took(turn: Turn): void {
    this.#turns.push(turn);
  }

  /** Replace all turns with a summary. Affects the view only; the call log keeps every turn. */
  collapse(summary: string): void {
    this.#turns.length = 0;
    this.#summary = summary;
  }
}
