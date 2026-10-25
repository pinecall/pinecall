/** The page's ways into a walk with no call: the section scrolled to offers its own, and the site's own button plays one. */
//
// The site marks a section with `data-pinecall-walk="<walk>"`: as the page is scrolled to it (its box
// across the screen's middle), the tutor offers that walk for a few seconds beside the face. A button
// the site draws and marks `data-pinecall-play="<walk>"` is shown (its `hidden` taken off) while that
// walk can play, and a click on it plays it. Both only for the walks the agent published.

/** The attribute a section names its walk with. */
export const WALK_ATTRIBUTE = "data-pinecall-walk";
/** The attribute the site's own button names its walk with. */
export const PLAY_ATTRIBUTE = "data-pinecall-play";

/** The line across the screen a section must cross to be the one scrolled to, as a share of the screen's height. */
const MIDDLE = 0.5;

export interface SectionsOptions {
  /** The section scrolled to names a published walk, by its name. */
  onReach: (name: string) => void;
  /** The site's own button for a walk clicked, by the walk's name. */
  onPlay: (name: string) => void;
}

export class Sections {
  readonly #document: Document;
  readonly #options: SectionsOptions;
  #names: string[] = [];
  #on = false;
  /** The section across the screen's middle at the last frame. */
  #at: Element | null = null;
  readonly #clicked = (event: Event): void => {
    const button = event.target instanceof Element ? event.target.closest(`[${PLAY_ATTRIBUTE}]`) : null;
    const name = button?.getAttribute(PLAY_ATTRIBUTE) ?? null;
    if (!this.#on || name === null || !this.#names.includes(name)) return;
    event.preventDefault();
    this.#options.onPlay(name);
  };

  constructor(document: Document, options: SectionsOptions) {
    this.#document = document;
    this.#options = options;
    document.addEventListener("click", this.#clicked);
  }

  /** The names of the walks the agent published. */
  offer(names: string[]): void {
    this.#names = names;
  }

  /**
   * Note the section scrolled to, and say so when it is a new one naming a published walk and `on`;
   * show the site's own buttons while `on`, for a published walk. Called every frame.
   */
  place(on: boolean): void {
    this.#on = on;
    for (const button of this.#document.querySelectorAll<HTMLElement>(`[${PLAY_ATTRIBUTE}]`)) {
      const hidden = !on || !this.#names.includes(button.getAttribute(PLAY_ATTRIBUTE) ?? "");
      if (button.hidden !== hidden) button.hidden = hidden;
    }
    const middle = (this.#document.defaultView?.innerHeight ?? 0) * MIDDLE;
    const at =
      [...this.#document.querySelectorAll(`[${WALK_ATTRIBUTE}]`)].find((section) => {
        const box = section.getBoundingClientRect();
        return box.height > 0 && box.top <= middle && box.bottom > middle;
      }) ?? null;
    if (at === this.#at) return;
    this.#at = at;
    const name = at?.getAttribute(WALK_ATTRIBUTE) ?? null;
    if (on && name !== null && this.#names.includes(name)) this.#options.onReach(name);
  }

  close(): void {
    this.#document.removeEventListener("click", this.#clicked);
  }
}
