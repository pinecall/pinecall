/** What a page gives `tutor()`: where it rests, its colour and shape, whose words show, the walks it plays, and the views of its own tools; and the tutor it hands back. */

import type { Shape } from "../face/shape.js";
import type { DoorRequest } from "../wire/ask.js";
import type { Captions } from "./captions.js";
import type { Views } from "./views.js";
import type { Walked } from "./walking.js";

export interface TutorOptions {
  /** The corner it rests in. Default `right`. */
  dock?: "right" | "left" | undefined;
  /** What the face is called for a screen reader. Default "Talk to the assistant". */
  label?: string | undefined;
  /** The face was clicked: the page starts the call, or ends it. */
  onClick?: (() => void) | undefined;
  /** How long its last words stay beside it after a reply, and the visitor's after theirs, in ms. Default 2600. */
  linger?: number | undefined;
  /** The face's shape: `circle` (the default), `squircle` or `blob`. */
  shape?: Shape | undefined;
  /** The face's and the pointer's colour, any CSS colour; the page's `--pc-face` when left out. */
  color?: string | undefined;
  /** Whose words show: `both` (the default), `agent`, `caller` or `none`. The visitor turns them off and on with CC, unless `none`. */
  captions?: Captions | undefined;
  /** The buttons' names, for a screen reader and a tooltip. Default "Hang up", "Captions", "Explain this", "Walks", "Stop", "Pause", "Close" and "More walks". */
  words?: {
    hangUp?: string | undefined;
    captions?: string | undefined;
    explain?: string | undefined;
    walks?: string | undefined;
    stop?: string | undefined;
    pause?: string | undefined;
    /** The buttons that take a walk a sentence back and on: "Back", "Next". */
    back?: string | undefined;
    next?: string | undefined;
    close?: string | undefined;
    more?: string | undefined;
    ask?: string | undefined;
    askAgent?: string | undefined;
    looking?: string | undefined;
    notHere?: string | undefined;
    forAgent?: string | undefined;
  } | undefined;
  /** Where the agent published its recorded walks (`GET …/v1/agents/{slug}/public/walks`): a button beside the face plays them with no call. */
  walks?: string | undefined;
  /** A walk started, ended, or was stopped: the page's own analytics hear it. */
  onWalk?: ((walked: Walked) => void) | undefined;
  /**
   * What the page draws for the agent's own tools, by tool name: a card beside the face with the free
   * times, the booking form, a piece of code. Read each time a tool finishes, so a page may set it late.
   */
  views?: Views | undefined;
  /**
   * The site's door, on its own server, answered by `@pinecall/dot/server`'s `answer()`: what the visitor
   * typed decided (`{ decide }`), the row of a table a walk read that answers them (`{ row }`), a walk's
   * sentence with slots recorded (`{ say }`). Given, the walks' menu has a field: "Ask me to show you…".
   */
  ask?: ((request: DoorRequest) => Promise<unknown>) | undefined;
  /** With `ask`, the field in the walks' menu; false leaves it out, for a door that only reads the page aloud. Default true. */
  typing?: boolean | undefined;
  /**
   * The page read aloud in the agent's voice, with no call: what it marks `data-pinecall-read`, the part read lit and
   * pointed at, its examples (`data-pinecall-press`) pressed on the way. The title of its pill, first in the walks' menu:
   * "Leer el capítulo". Each part is recorded by the site's door (`{ read }`), so it takes `ask`.
   */
  reading?: string | undefined;
  /** What they typed, for a question the page cannot show: the site takes it to the agent (a call, it written in). */
  onTalk?: ((message: string) => void) | undefined;
}
export interface Tutor {
  /** A message the agent sent on `pinecall.ui`: true when it was the tutor's to carry out, false for a card or choices. */
  take(data: unknown): boolean;
  /** Let the face hear the voice: call it from the click that starts the call. */
  wake(): void;
  /** Read the page aloud (`reading`), from the visitor's click: a button of the site's own. */
  read(): void;
  /** Stop the walk or the reading playing, if one is: the site's own reason to (the visitor took over). */
  stop(): void;
  close(): void;
}
