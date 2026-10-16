/** How a call opens and when the agent may end it, as a class declares them: `improvise`, `Opening`, `Ending`. */

/** The model opens the call: on its prompt alone, or with an instruction for this opening. */
export interface Improvised {
  readonly improvise: string;
  readonly interruptible?: boolean;
}

/**
 * Let the model open the call. `static greeting = improvise` opens on the prompt alone;
 * `improvise("Greet them by name if you know it")` adds an instruction for the opening.
 * The caller cannot cut it short unless `{ interruptible: true }`.
 */
export function improvise(instruction = "", options: { interruptible?: boolean } = {}): Improvised {
  return options.interruptible === undefined ? { improvise: instruction } : { improvise: instruction, interruptible: options.interruptible };
}

/**
 * How a call opens: words said as written (a string, or `{ text, interruptible }`), or the model's
 * own (`improvise`, `improvise("…")`). The caller cannot cut it short unless it is interruptible.
 */
export type Opening = string | { text: string; interruptible?: boolean } | Improvised | typeof improvise;

/** When the model may end the call: in your words, or `true` whenever it judges the call done. */
export type Ending = string | true;
