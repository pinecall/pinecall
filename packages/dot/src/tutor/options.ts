/** What a page gives `tutor()`: where it rests, its colour and shape, whose words show, the walks it plays, and the views of its own tools. */

import type { Shape } from "../face/shape.js";
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
    close?: string | undefined;
    more?: string | undefined;
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
}
