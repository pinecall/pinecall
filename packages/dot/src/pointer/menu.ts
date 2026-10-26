/** The walks a visitor may play with no call: a small button beside the resting face, its pills fanned in an arc round it. */
//
// The button sits on the face's shoulder, toward the page, in front of the face: behind it, a click
// meant for it reached the face and began a call. A click fans the walks out beside the
// face, each a pill with its title and length, read from the top: the first walk is the highest. Escape, a click elsewhere or
// a pick closes them. The walk of the section the visitor is on is marked, and the page it stands on is the
// one that opens. Every colour is the person's: --pc-face, --pc-bubble, --pc-bubble-ink.

import { clock } from "../wire/index.js";
import type { Asking } from "./asking.js";
import type { Point } from "./flight.js";

/** A pill's height, in px. */
const PILL = 24;

const STYLE = `
.pc-walks { position: fixed; z-index: 3; width: 22px; height: 22px; padding: 0; border: 2px solid var(--pc-bubble, #fff); border-radius: 50%;
  background: var(--pc-face, #1f6b55); color: #fff; font: 700 10px/18px system-ui, sans-serif; text-align: center; cursor: pointer;
  pointer-events: auto; box-shadow: 0 2px 8px rgb(0 0 0 / .2); transition: transform .15s; }
.pc-walks:hover, .pc-walks[aria-expanded="true"] { transform: scale(1.12); }
.pc-walks:focus-visible, .pc-pill:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
.pc-walks[hidden], .pc-pill[hidden] { display: none; }
.pc-pill { position: fixed; z-index: 3; display: flex; align-items: center; gap: 6px; height: ${PILL}px; padding: 0 10px 0 8px; border: 0;
  border-radius: 999px; background: var(--pc-bubble, #fff); color: var(--pc-bubble-ink, #17201c); cursor: pointer; pointer-events: auto;
  font: 500 12px/${PILL}px system-ui, -apple-system, "Segoe UI", sans-serif; white-space: nowrap; box-shadow: 0 4px 14px rgb(0 0 0 / .16);
  opacity: 0; transform: scale(.85); transition: opacity .18s, transform .18s; }
.pc-pill.pc-shown { opacity: 1; transform: none; }
.pc-pill.pc-here { background: var(--pc-face, #1f6b55); color: #fff; box-shadow: 0 0 0 3px color-mix(in srgb, var(--pc-face, #1f6b55) 30%, transparent), 0 4px 14px rgb(0 0 0 / .2); }
.pc-pill.pc-here .pc-tri { border-left-color: #fff; }
.pc-pill.pc-here .pc-long { opacity: .8; }
.pc-pill .pc-tri { width: 0; height: 0; border-style: solid; border-width: 4px 0 4px 6px; border-color: transparent transparent transparent var(--pc-face, #1f6b55); }
.pc-pill .pc-long { opacity: .55; font-variant-numeric: tabular-nums; }
.pc-more { position: fixed; z-index: 3; display: grid; place-items: center; width: ${PILL}px; height: ${PILL}px; padding: 0; border: 0;
  border-radius: 50%; background: var(--pc-bubble, #fff); color: var(--pc-face, #1f6b55); cursor: pointer; pointer-events: auto;
  box-shadow: 0 4px 14px rgb(0 0 0 / .16); }
.pc-more[hidden] { display: none; }
.pc-more svg { transition: transform .2s; }
.pc-more.pc-last svg { transform: rotate(180deg); }
.pc-more:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { .pc-pill, .pc-walks, .pc-more svg { transition: none; } }
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
  /** The place in the list of the walk of the section the visitor is on, or -1 when none is. */
  current: () => number;
  /** What the button that shows the next pills is called for a screen reader: "More walks". */
  more: string;
  /** The field for what the visitor wants shown, above the pills while the menu is open; the menu then opens with no walks too. */
  ask?: Asking | undefined;
}

/** How many pills show at once; the rest come a page at a time, from a small button under them. */
export const PAGE = 4;

/** How far apart two pills stand, in px: a pill's height and a gap of 6, so no two ever overlap. */
export const STEP = PILL + 6;

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
  readonly #more: HTMLButtonElement;
  #pills: HTMLButtonElement[] = [];
  #open = false;
  /** Which page of pills shows, from 0. */
  #page = 0;
  readonly #outside = (event: Event): void => {
    const target = event.target instanceof Node ? event.target : null;
    const parts: Element[] = [this.#button, this.#more, ...this.#pills, ...(this.#options.ask ? [this.#options.ask.element] : [])];
    if (target !== null && parts.some((part) => part.contains(target))) return;
    this.toggle(false);
  };
  readonly #escape = (event: KeyboardEvent): void => {
    if (event.key === "Escape") this.toggle(false);
  };
  // The face rests in a corner of the window, so a resize moves it, and the button and pills with it.
  readonly #resized = (): void => this.#place();
  /** The walk marked now, by its place in the list; -1 for none. */
  #here = -1;
  // While the menu is open the mark follows the page: when the visitor scrolls into another section its walk is
  // marked, and its page shown; a visitor paging within one section is left where they are.
  readonly #scrolled = (): void => {
    if (!this.#open) return;
    const here = this.#options.current();
    if (here === this.#here) return;
    this.#mark(here);
    if (here >= 0) this.#page = Math.floor(here / PAGE);
    this.#show();
  };

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
    this.#more = document.createElement("button");
    this.#more.type = "button";
    this.#more.className = "pc-more";
    this.#more.hidden = true;
    this.#more.innerHTML = `<svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    this.#more.setAttribute("aria-label", options.more);
    this.#more.title = options.more;
    this.#more.addEventListener("click", () => {
      this.#page = (this.#page + 1) % Math.ceil(this.#pills.length / PAGE);
      this.#show();
      this.#shown()[0]?.focus();
    });
    host(this.#more);
    this.#host = host;
    document.addEventListener("pointerdown", this.#outside, true);
    document.addEventListener("keydown", this.#escape);
    document.defaultView?.addEventListener("resize", this.#resized);
    document.defaultView?.addEventListener("scroll", this.#scrolled, { passive: true });
  }

  /** The walks to offer; none hides the button. */
  offer(items: MenuItem[]): void {
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
    this.#button.hidden = items.length === 0 && this.#options.ask === undefined;
  }

  /** Whether the button may show now: not during a call, nor while a walk plays. */
  available(on: boolean): void {
    this.#button.hidden = !on || (this.#pills.length === 0 && this.#options.ask === undefined);
    if (!on) this.toggle(false);
    if (on) this.#place();
  }

  /** Fan the pills out, or fold them back. */
  toggle(open: boolean): void {
    this.#open = open && !this.#button.hidden;
    // It opens on the page of the walk of the section the visitor is on, and marks it.
    const here = this.#open ? this.#options.current() : -1;
    this.#page = here < 0 ? 0 : Math.floor(here / PAGE);
    this.#mark(here);
    this.#button.setAttribute("aria-expanded", String(this.#open));
    this.#show();
    if (!this.#open) return;
    if (this.#options.ask) this.#options.ask.focus();
    else this.#shown()[0]?.focus();
  }

  #mark(here: number): void {
    this.#here = here;
    this.#pills.forEach((pill, index) => pill.classList.toggle("pc-here", index === here));
  }

  /** The pills of the page showing, while the pills are fanned out. */
  #shown(): HTMLButtonElement[] {
    return this.#open ? this.#pills.slice(this.#page * PAGE, (this.#page + 1) * PAGE) : [];
  }

  // The page's pills shown, one after another; the others folded; the button for more while there are more than a page.
  #show(): void {
    this.#place();
    const shown = this.#shown();
    for (const pill of this.#pills) {
      if (shown.includes(pill)) continue;
      pill.hidden = true;
      pill.classList.remove("pc-shown");
    }
    shown.forEach((pill, index) => {
      pill.hidden = false;
      setTimeout(() => pill.classList.add("pc-shown"), 30 * index);
    });
    this.#more.hidden = !this.#open || this.#pills.length <= PAGE;
    this.#options.ask?.show(this.#open);
    this.#more.classList.toggle("pc-last", (this.#page + 1) * PAGE >= this.#pills.length);
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
    const right = this.#options.dock === "right";
    const stand = (pill: HTMLButtonElement | undefined, point: Point): void => {
      if (pill === undefined) return;
      Object.assign(pill.style, {
        top: `${point.y - PILL / 2}px`,
        left: right ? "auto" : `${point.x}px`,
        right: right ? `${(view?.innerWidth ?? 0) - point.x}px` : "auto",
        transformOrigin: right ? "right center" : "left center",
      });
    };
    // The page's pills from the top, the first the highest; under them, the button for more.
    const shown = this.#shown();
    const paged = this.#pills.length > PAGE;
    const slots = fanned(shown.length + (paged ? 1 : 0), at, radius, this.#options.dock);
    shown.forEach((pill, index) => stand(pill, slots[slots.length - 1 - index] ?? at));
    // The field stands above the highest pill, or beside the face when there is none.
    const [beside] = fanned(1, at, radius, this.#options.dock);
    const highest = slots[slots.length - 1] ?? beside;
    if (this.#options.ask && highest !== undefined) {
      const bottom = (view?.innerHeight ?? 0) - highest.y + (slots.length > 0 ? PILL / 2 + 8 : -PILL / 2);
      this.#options.ask.place(bottom, right ? (view?.innerWidth ?? 0) - highest.x : highest.x, right);
    }
    const [under] = slots;
    if (paged && under !== undefined) {
      Object.assign(this.#more.style, { left: `${right ? under.x - PILL : under.x}px`, top: `${under.y - PILL / 2}px` });
    }
  }

  close(): void {
    this.#document.removeEventListener("pointerdown", this.#outside, true);
    this.#document.removeEventListener("keydown", this.#escape);
    this.#document.defaultView?.removeEventListener("resize", this.#resized);
    this.#document.defaultView?.removeEventListener("scroll", this.#scrolled);
    this.#button.remove();
    this.#more.remove();
    for (const pill of this.#pills) pill.remove();
    this.#style.remove();
  }
}
