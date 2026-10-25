/** The page's ways into a walk with no call: a small ▶ in the corner of a section that names one, or the site's own button. */
//
// The site marks a section with `data-pinecall-walk="<walk>"`; the button stands inside its top left
// corner while the corner is on the screen, for the walks the agent published. It lives on the
// person's layer, out of what the agent reads, and follows its section every frame, as the page
// scrolls or changes. Where a corner does not suit, the site draws its own button and marks it
// `data-pinecall-play="<walk>"`: it is shown (its `hidden` taken off) while that walk can play, and
// a click on it plays it. Colours: --pc-face.

import { clock } from "../wire/index.js";

/** The attribute a section names its walk with. */
export const WALK_ATTRIBUTE = "data-pinecall-walk";
/** The attribute the site's own button names its walk with. */
export const PLAY_ATTRIBUTE = "data-pinecall-play";

/** How far in from the section's corner the button stands, and its size, in px. */
const INSET = 20;
const SIZE = 24;

const STYLE = `
.pc-corner { all: unset; position: fixed; box-sizing: border-box; display: grid; place-items: center; width: ${SIZE}px; height: ${SIZE}px;
  border-radius: 50%; cursor: pointer; pointer-events: auto; color: var(--pc-face, #1f6b55); opacity: .6;
  transition: background-color .18s, opacity .18s; }
.pc-corner:hover, .pc-corner:focus-visible { opacity: 1; background: color-mix(in srgb, var(--pc-face, #1f6b55) 16%, transparent); }
.pc-corner:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
.pc-corner[hidden] { display: none; }
.pc-corner svg { display: block; margin-left: 2px; fill: currentColor; }
@media (prefers-reduced-motion: reduce) { .pc-corner { transition: none; } }
`;

const PLAY = `<svg viewBox="0 0 10 12" width="8" height="10" aria-hidden="true"><path d="M1 1.2v9.6c0 .6.7 1 1.2.6l7-4.8c.4-.3.4-.9 0-1.2l-7-4.8C1.7.2 1 .6 1 1.2Z"/></svg>`;

/** One walk a corner may play: its name, as the section names it, its title and its length. */
export interface CornerWalk {
  name: string;
  title: string;
  ms: number;
}

export interface CornersOptions {
  /** How the button is called for a screen reader, before the walk's title: "Play". */
  label: string;
  /** A corner's walk picked, by its name. */
  onPlay: (name: string) => void;
}

export class Corners {
  readonly #document: Document;
  readonly #host: (element: Element) => void;
  readonly #options: CornersOptions;
  readonly #style: HTMLStyleElement;
  readonly #buttons = new Map<Element, HTMLButtonElement>();
  #walks: CornerWalk[] = [];
  #on = false;
  readonly #clicked = (event: Event): void => {
    const button = event.target instanceof Element ? event.target.closest(`[${PLAY_ATTRIBUTE}]`) : null;
    const name = button?.getAttribute(PLAY_ATTRIBUTE);
    if (!this.#on || name === null || name === undefined || !this.#walks.some((walk) => walk.name === name)) return;
    event.preventDefault();
    this.#options.onPlay(name);
  };

  constructor(document: Document, host: (element: Element) => void, options: CornersOptions) {
    this.#document = document;
    this.#host = host;
    this.#options = options;
    this.#style = document.createElement("style");
    this.#style.textContent = STYLE;
    document.head.append(this.#style);
    document.addEventListener("click", this.#clicked);
  }

  /** The walks the agent published: a section naming one gets its button. */
  offer(walks: CornerWalk[]): void {
    this.#walks = walks;
    for (const button of this.#buttons.values()) button.remove();
    this.#buttons.clear();
  }

  /**
   * Each button onto its section's corner, shown while `on` and the corner is on the screen; the
   * site's own buttons shown while `on`, for a walk published. Called every frame.
   */
  place(on: boolean): void {
    this.#on = on;
    for (const button of this.#document.querySelectorAll<HTMLElement>(`[${PLAY_ATTRIBUTE}]`)) {
      const hidden = !on || !this.#walks.some((walk) => walk.name === button.getAttribute(PLAY_ATTRIBUTE));
      if (button.hidden !== hidden) button.hidden = hidden;
    }
    this.#follow();
    const view = this.#document.defaultView;
    const height = view?.innerHeight ?? 0;
    for (const [section, button] of this.#buttons) {
      const box = section.getBoundingClientRect();
      const left = Math.max(box.left, 0) + INSET;
      const top = box.top + INSET;
      const hidden = !on || top < 0 || top + SIZE > height || box.width === 0;
      if (button.hidden !== hidden) button.hidden = hidden;
      if (hidden) continue;
      button.style.left = `${left.toFixed(0)}px`;
      button.style.top = `${top.toFixed(0)}px`;
    }
  }

  close(): void {
    this.#document.removeEventListener("click", this.#clicked);
    for (const button of this.#buttons.values()) button.remove();
    this.#buttons.clear();
    this.#style.remove();
  }

  // The sections naming a walk, as the page is now: a button for each new one, none kept for one gone.
  #follow(): void {
    const sections = new Set(this.#document.querySelectorAll(`[${WALK_ATTRIBUTE}]`));
    for (const [section, button] of this.#buttons) {
      if (sections.has(section)) continue;
      button.remove();
      this.#buttons.delete(section);
    }
    for (const section of sections) {
      if (this.#buttons.has(section)) continue;
      const walk = this.#walks.find((one) => one.name === section.getAttribute(WALK_ATTRIBUTE));
      if (walk !== undefined) this.#buttons.set(section, this.#button(walk));
    }
  }

  #button(walk: CornerWalk): HTMLButtonElement {
    const button = this.#document.createElement("button");
    button.type = "button";
    button.className = "pc-corner";
    button.hidden = true;
    button.innerHTML = PLAY;
    const label = `${this.#options.label}: ${walk.title} (${clock(walk.ms)})`;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.addEventListener("click", () => this.#options.onPlay(walk.name));
    this.#host(button);
    return button;
  }
}
