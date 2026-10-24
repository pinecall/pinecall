/** What the tutor shows of the conversation in words: whose, as the site chose and the visitor turned on or off, and the visitor's own words as they say them. */
//
// The agent's words are lit as its voice says them (the bubble beside the face); the visitor's are
// what the ears hear, interim and then final, held a moment after their turn ends. The site picks
// which sides may show; the visitor's CC button turns them off and on, kept in their browser.

import type { RoomStore } from "@pinecall/room";

/** Whose words the tutor may show: both sides, one, or none. */
export type Captions = "both" | "agent" | "caller" | "none";
export const CAPTIONS: readonly Captions[] = ["both", "agent", "caller", "none"];

/** Where the visitor's choice is kept, per site. */
const KEPT = "pinecall.captions";

/** What of the call's log the visitor's words are read from. */
export type Heard = Pick<RoomStore["state"]["log"], "live" | "turns">;

/** `value` when it names a choice, else both sides. */
export function captionsOf(value: string | null | undefined): Captions {
  return CAPTIONS.find((one) => one === value) ?? "both";
}

/** Whether `side`'s words show, under the site's choice and the visitor's. */
export function shows(captions: Captions, visitorOn: boolean, side: "agent" | "caller"): boolean {
  return visitorOn && (captions === "both" || captions === side);
}

// Storage throws in a private window or with site data blocked: the captions are then simply on.
/** Whether the visitor left the captions on: on unless they turned them off on this site. */
export function visitorWantsCaptions(storage: () => Storage): boolean {
  try {
    return storage().getItem(KEPT) !== "off";
  } catch {
    return true;
  }
}

/** Keep the visitor's choice for their next visit. */
export function keepVisitorChoice(storage: () => Storage, on: boolean): void {
  try {
    storage().setItem(KEPT, on ? "on" : "off");
  } catch {
    // Not kept: it holds for this page.
  }
}

/** The visitor's words to show now: what they are saying, else their last turn for `linger` ms after it ended. */
export class Hearing {
  readonly #linger: number;
  #last = { text: "", at: Number.NEGATIVE_INFINITY };
  /** The visitor's turns already seen; null until the first look, so a page that joins late shows none of the past. */
  #turns: number | null = null;

  constructor(linger: number) {
    this.#linger = linger;
  }

  at(log: Heard, now: number): string | null {
    const turns = log.turns.filter((turn) => turn.role === "user");
    if (this.#turns === null) this.#turns = turns.length;
    const saying = log.live.user;
    if (saying !== null && saying !== "") {
      this.#last = { text: saying, at: now };
      return saying;
    }
    if (turns.length > this.#turns) {
      this.#turns = turns.length;
      this.#last = { text: turns.at(-1)?.text ?? "", at: now };
    }
    return this.#last.text !== "" && now - this.#last.at < this.#linger ? this.#last.text : null;
  }
}
