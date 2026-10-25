/** The walks a visitor may play with no call: a small button beside the resting face, its pills fanned in an arc round it. */
//
// The button sits on the face's shoulder, toward the page, in front of the face: behind it, a click
// meant for it reached the face and began a call. A click fans the walks out beside the
// face, each a pill with its title and length, read from the top: the first walk is the highest. Escape, a click elsewhere or
// a pick closes them. One walk can also be offered alone, beside the face, for a few seconds: the one
// of the section scrolled to. Every colour is the person's: --pc-face, --pc-bubble, --pc-bubble-ink.

import { clock } from "../wire/index.js";
import type { Point } from "./flight.js";

const STYLE = `
.pc-walks { position: fixed; z-index: 3; width: 22px; height: 22px; padding: 0; border: 2px solid var(--pc-bubble, #fff); border-radius: 50%;
  background: var(--pc-face, #1f6b55); color: #fff; font: 700 10px/18px system-ui, sans-serif; text-align: center; cursor: pointer;
  pointer-events: auto; box-shadow: 0 2px 8px rgb(0 0 0 / .2); transition: transform .15s; }
.pc-walks:hover, .pc-walks[aria-expanded="true"] { transform: scale(1.12); }
.pc-walks:focus-visible, .pc-pill:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
.pc-walks[hidden], .pc-pill[hidden] { display: none; }
.pc-pill { position: fixed; z-index: 3; display: flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px 0 9px; border: 0;
  border-radius: 999px; background: var(--pc-bubble, #fff); color: var(--pc-bubble-ink, #17201c); cursor: pointer; pointer-events: auto;
  font: 500 13px/30px system-ui, -apple-system, "Segoe UI", sans-serif; white-space: nowrap; box-shadow: 0 6px 18px rgb(0 0 0 / .16);
  opacity: 0; transform: scale(.85); transition: opacity .18s, transform .18s; }
.pc-pill.pc-shown { opacity: 1; transform: none; }
.pc-pill .pc-tri { width: 0; height: 0; border-style: solid; border-width: 5px 0 5px 8px; border-color: transparent transparent transparent var(--pc-face, #1f6b55); }
.pc-pill .pc-long { opacity: .55; font-variant-numeric: tabular-nums; }
@media (prefers-reduced-motion: reduce) { .pc-pill, .pc-walks { transition: none; } }
`;

/** One walk as its pill shows it. */
export interface MenuItem {
  title: string;
  ms: number;
}

export interface MenuOptions {
  dock: "right" | "left";
  /** What the button is called for a screen reader: "Walks". */
  label: string;
  /** Where the resting face's middle is, and its radius, now. */
  face: () => { at: Point; radius: number };
  /** A walk picked, by its place in the list. */
  onPick: (index: number) => void;
}

/** How long a walk offered alone stays beside the face, in ms. */
export const OFFERED_MS = 5000;

/** How far apart two pills stand, in px: a pill's 30 and a gap of 10, so no two ever overlap. */
export const STEP = 40;

/** How far the nearest pill stands from the face's edge, and how much farther each lower one does, in px. */
const GAP = 14;
const SLANT = 10;

/**
 * Where each of `count` pills sits beside a face at `at` of `radius`, the end nearest it: rising a
 * step at a time from beside the face, each a slant nearer it than the one below, the highest a gap
 * from its edge. On an arc wide enough for the highest, the lowest stood far out from the face.
 */
export function fanned(count: number, at: Point, radius: number, dock: "right" | "left"): Point[] {
  const side = dock === "right" ? -1 : 1;
  const lowest = radius * 0.3;
  return Array.from({ length: count }, (_, index) => ({
    x: at.x + side * (radius + GAP + (count - 1 - index) * SLANT),
    y: at.y - lowest - index * STEP,
  }));
}

export class Menu {
  readonly #document: Document;
  readonly #options: MenuOptions;
  readonly #style: HTMLStyleElement;
  readonly #button: HTMLButtonElement;
  readonly #host: (element: Element) => void;
  #pills: HTMLButtonElement[] = [];
  #open = false;
  /** The walk offered alone, by its place in the list, and when it goes. */
  #alone: { index: number; timer: ReturnType<typeof setTimeout> } | null = null;
  readonly #outside = (event: Event): void => {
    const target = event.target instanceof Node ? event.target : null;
    if (target !== null && (this.#button.contains(target) || this.#pills.some((pill) => pill.contains(target)))) return;
    this.toggle(false);
  };
  readonly #escape = (event: KeyboardEvent): void => {
    if (event.key === "Escape") this.toggle(false);
  };
  // The face rests in a corner of the window, so a resize moves it, and the button and pills with it.
  readonly #resized = (): void => this.#place();

  constructor(document: Document, host: (element: Element) => void, options: MenuOptions) {
    this.#document = document;
    this.#options = options;
    this.#style = document.createElement("style");
    this.#style.textContent = STYLE;
    document.head.append(this.#style);
    this.#button = document.createElement("button");
    this.#button.type = "button";
    this.#button.className = "pc-walks";
    this.#button.hidden = true;
    this.#button.textContent = "▸";
    this.#button.setAttribute("aria-label", options.label);
    this.#button.setAttribute("aria-expanded", "false");
    this.#button.title = options.label;
    this.#button.addEventListener("click", () => this.toggle(!this.#open));
    host(this.#button);
    this.#host = host;
    document.addEventListener("pointerdown", this.#outside, true);
    document.addEventListener("keydown", this.#escape);
    document.defaultView?.addEventListener("resize", this.#resized);
  }

  /** The walks to offer; none hides the button. */
  offer(items: MenuItem[]): void {
    this.#unsuggest();
    for (const pill of this.#pills) pill.remove();
    this.#pills = items.map((item, index) => {
      const pill = this.#document.createElement("button");
      pill.type = "button";
      pill.className = "pc-pill";
      pill.hidden = true;
      const tri = this.#document.createElement("span");
      tri.className = "pc-tri";
      const long = this.#document.createElement("span");
      long.className = "pc-long";
      long.textContent = clock(item.ms);
      pill.append(tri, this.#document.createTextNode(item.title), long);
      pill.addEventListener("click", () => {
        this.toggle(false);
        this.#options.onPick(index);
      });
      this.#host(pill);
      return pill;
    });
    this.#button.hidden = items.length === 0;
  }

  /** Whether the button may show now: not during a call, nor while a walk plays. */
  available(on: boolean): void {
    this.#button.hidden = !on || this.#pills.length === 0;
    if (!on) this.toggle(false);
    if (on) this.#place();
  }

  /** Offer one walk alone, beside the face, for `ms`, while the button shows and the pills are folded. */
  suggest(index: number, ms = OFFERED_MS): void {
    const pill = this.#pills[index];
    if (pill === undefined || this.#open || this.#button.hidden) return;
    this.#unsuggest();
    this.#alone = { index, timer: setTimeout(() => this.#unsuggest(), ms) };
    this.#place();
    pill.hidden = false;
    setTimeout(() => pill.classList.add("pc-shown"), 30);
  }

  /** Fan the pills out, or fold them back. */
  toggle(open: boolean): void {
    this.#unsuggest();
    this.#open = open && !this.#button.hidden;
    this.#button.setAttribute("aria-expanded", String(this.#open));
    this.#place();
    this.#pills.forEach((pill, index) => {
      pill.hidden = !this.#open;
      if (!this.#open) return void pill.classList.remove("pc-shown");
      setTimeout(() => pill.classList.add("pc-shown"), 30 * index);
    });
    if (this.#open) this.#pills[0]?.focus();
  }

  get open(): boolean {
    return this.#open;
  }

  #place(): void {
    const { at, radius } = this.#options.face();
    const lean = radius * 0.72 + 2;
    const side = this.#options.dock === "right" ? -1 : 1;
    Object.assign(this.#button.style, { left: `${at.x + side * lean - 11}px`, top: `${at.y - lean - 11}px` });
    const view = this.#document.defaultView;
    const count = this.#pills.length;
    const right = this.#options.dock === "right";
    const stand = (pill: HTMLButtonElement | undefined, point: Point): void => {
      if (pill === undefined) return;
      Object.assign(pill.style, {
        top: `${point.y - 15}px`,
        left: right ? "auto" : `${point.x}px`,
        right: right ? `${(view?.innerWidth ?? 0) - point.x}px` : "auto",
        transformOrigin: right ? "right center" : "left center",
      });
    };
    fanned(count, at, radius, this.#options.dock).forEach((point, index) => stand(this.#pills[count - 1 - index], point));
    // A walk offered alone stands where the lowest pill would, beside the face.
    const [beside] = fanned(1, at, radius, this.#options.dock);
    if (this.#alone !== null && beside !== undefined) stand(this.#pills[this.#alone.index], beside);
  }

  #unsuggest(): void {
    if (this.#alone === null) return;
    clearTimeout(this.#alone.timer);
    const { index } = this.#alone;
    const pill = this.#pills[index];
    this.#alone = null;
    if (pill === undefined || this.#open) return;
    pill.classList.remove("pc-shown");
    // Hidden once it has faded, unless it was offered again or the pills fanned out meanwhile.
    setTimeout(() => {
      if (!this.#open && this.#alone?.index !== index) pill.hidden = true;
    }, 200);
  }

  close(): void {
    this.#unsuggest();
    this.#document.removeEventListener("pointerdown", this.#outside, true);
    this.#document.removeEventListener("keydown", this.#escape);
    this.#document.defaultView?.removeEventListener("resize", this.#resized);
    this.#button.remove();
    for (const pill of this.#pills) pill.remove();
    this.#style.remove();
  }
}
