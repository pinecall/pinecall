/** The tutor as one more person on the page: a pointer of its own, its face beside the tip, what it says beside the face. */
//
// One fixed layer over the page that takes no clicks but on the face. Resting, the face sits in a
// corner like the widget's button; touring, it shrinks beside the tip of an arrow in its colour,
// the way a multiplayer cursor carries a name tag. The spotlight and the "here" ring live there too,
// and, in the corner it rests in, what the visitor is saying and the buttons: captions, with hang-up
// in a call and stop in a walk. They stand beside the resting face, and slide into its corner while
// it tours, back aside as it comes home. Every colour is a custom property: --pc-face
// (the dot and the arrow), --pc-face-ring, --pc-bubble, --pc-bubble-ink, --pc-heard, --pc-heard-ink,
// --pc-hang.

import type { Kind } from "./hover.js";
import { ARROW, BACK, CAPTIONS, NEXT, PAUSE, STOP } from "./icons.js";
import type { Point } from "./flight.js";

/** The resting face's size, in px, and how far its edge stands from the corner of the window. */
const SIZE = 58;
const EDGE = 14;

const STYLE = `
.pc-layer { position: fixed; inset: 0; pointer-events: none; z-index: 2147483000; }
.pc-person { position: fixed; left: 0; top: 0; z-index: 2; will-change: transform; }
.pc-arrow { position: absolute; left: -3px; top: -2px; width: 26px; height: 26px; opacity: 0; transition: opacity .25s; filter: drop-shadow(0 2px 3px rgb(0 0 0 / .35)); }
.pc-person.pc-touring .pc-arrow { opacity: 1; }
.pc-arrow path { display: none; }
.pc-arrow[data-kind="arrow"] .pc-kind-arrow, .pc-arrow[data-kind="hand"] .pc-kind-hand, .pc-arrow[data-kind="ibeam"] .pc-kind-ibeam { display: inline; }
.pc-face { position: absolute; width: var(--pc-dot-size, ${SIZE}px); height: var(--pc-dot-size, ${SIZE}px); left: calc(var(--pc-dot-size, ${SIZE}px) / -2); top: calc(var(--pc-dot-size, ${SIZE}px) / -2);
  transition: width .45s cubic-bezier(.2,.8,.2,1), height .45s cubic-bezier(.2,.8,.2,1), left .45s cubic-bezier(.2,.8,.2,1), top .45s cubic-bezier(.2,.8,.2,1);
  pointer-events: auto; cursor: pointer; border-radius: 50%; }
.pc-face:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 3px; }
.pc-person.pc-touring .pc-face { width: 40px; height: 40px; left: 14px; top: 16px; }
.pc-progress { position: absolute; width: calc(var(--pc-dot-size, ${SIZE}px) + 12px); height: calc(var(--pc-dot-size, ${SIZE}px) + 12px);
  left: calc(var(--pc-dot-size, ${SIZE}px) / -2 - 6px); top: calc(var(--pc-dot-size, ${SIZE}px) / -2 - 6px); transform: rotate(-90deg); pointer-events: none;
  transition: width .45s cubic-bezier(.2,.8,.2,1), height .45s cubic-bezier(.2,.8,.2,1), left .45s cubic-bezier(.2,.8,.2,1), top .45s cubic-bezier(.2,.8,.2,1); }
.pc-progress[hidden] { display: none; }
.pc-progress circle { fill: none; stroke: var(--pc-face, #1f6b55); stroke-width: 2.5; stroke-linecap: round; }
.pc-person.pc-touring .pc-progress { width: 52px; height: 52px; left: 8px; top: 10px; }
.pc-bubble { position: absolute; width: max-content; max-width: min(270px, 70vw); right: -30px; bottom: calc(var(--pc-dot-size, ${SIZE}px) / 2 + 12px); padding: 9px 13px;
  background: var(--pc-bubble, #fff); color: var(--pc-bubble-ink, #17201c); border: 1px solid rgb(0 0 0 / .08); border-radius: 16px 16px 4px 16px;
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; box-shadow: 0 10px 28px rgb(0 0 0 / .14); transition: opacity .2s, transform .2s; transform-origin: bottom right; }
.pc-bubble[hidden] { display: block !important; opacity: 0; transform: scale(.94); }
.pc-bubble .pc-coming { opacity: .38; }
.pc-person.pc-touring .pc-bubble { right: auto; bottom: auto; left: 62px; top: 14px; border-radius: 4px 16px 16px 16px; transform-origin: top left; }
.pc-person.pc-touring.pc-west .pc-face { left: -54px; }
.pc-person.pc-touring.pc-west .pc-arrow { left: -23px; transform: scaleX(-1); }
.pc-person.pc-touring.pc-west .pc-progress { left: -60px; }
.pc-person.pc-touring.pc-west .pc-bubble { left: auto; right: 62px; border-radius: 16px 4px 16px 16px; transform-origin: top right; }
.pc-person.pc-touring.pc-up .pc-face { top: -56px; }
.pc-person.pc-touring.pc-up .pc-progress { top: -62px; }
.pc-person.pc-touring.pc-up .pc-bubble { top: auto; bottom: 14px; border-radius: 16px 16px 16px 4px; transform-origin: bottom left; }
.pc-person.pc-touring.pc-west.pc-up .pc-bubble { border-radius: 16px 16px 4px 16px; transform-origin: bottom right; }
.pc-person.pc-left:not(.pc-touring) .pc-bubble { right: auto; left: -30px; border-radius: 16px 16px 16px 4px; transform-origin: bottom left; }
.pc-heard { position: fixed; right: ${EDGE}px; bottom: calc(${EDGE}px + var(--pc-dot-size, ${SIZE}px) + 12px); width: max-content; max-width: min(270px, 70vw); padding: 9px 13px;
  background: var(--pc-heard, #e7f3ee); color: var(--pc-heard-ink, #17201c); border-radius: 16px 16px 4px 16px;
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; box-shadow: 0 10px 28px rgb(0 0 0 / .12); transition: opacity .2s; }
.pc-heard[hidden] { display: block !important; opacity: 0; }
.pc-calling { position: fixed; right: calc(${EDGE}px + var(--pc-dot-size, ${SIZE}px) + 8px); bottom: calc(${EDGE}px + var(--pc-dot-size, ${SIZE}px) / 2 - 16px); display: flex; gap: 2px; padding: 3px;
  border-radius: 999px; background: var(--pc-bubble, #fff); box-shadow: 0 4px 14px rgb(0 0 0 / .18); pointer-events: auto; transition: right .35s cubic-bezier(.2,.8,.2,1), left .35s cubic-bezier(.2,.8,.2,1); }
.pc-layer.pc-away .pc-calling { right: ${EDGE}px; }
.pc-calling[hidden] { display: none; }
.pc-calling button { all: unset; box-sizing: border-box; height: 26px; min-width: 26px; padding: 0 8px; border-radius: 999px; cursor: pointer;
  font: 600 11px/26px system-ui, -apple-system, "Segoe UI", sans-serif; text-align: center; color: var(--pc-bubble-ink, #17201c); }
.pc-calling button:hover { background: color-mix(in srgb, var(--pc-bubble-ink, #17201c) 9%, transparent); }
.pc-calling button:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
.pc-calling .pc-cc, .pc-calling .pc-pause, .pc-calling .pc-stop, .pc-calling .pc-back, .pc-calling .pc-next { display: grid; place-items: center; padding: 0; }
.pc-calling svg { display: block; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.pc-calling .pc-stop svg { fill: currentColor; stroke: none; }
.pc-pause .pc-go { display: none; fill: currentColor; stroke: none; }
.pc-pause[aria-pressed="true"] .pc-go { display: inline; }
.pc-pause[aria-pressed="true"] .pc-hold { display: none; }
.pc-cc .pc-off { display: none; }
.pc-cc[aria-pressed="false"] { opacity: .6; }
.pc-cc[aria-pressed="false"] .pc-off { display: inline; }
.pc-calling button[hidden] { display: none; }
.pc-calling .pc-hang, .pc-calling .pc-hang:hover { background: var(--pc-hang, #d6453d); color: #fff; font-size: 13px; }
.pc-play { position: fixed; width: 26px; height: 26px; border-radius: 50%; pointer-events: auto; cursor: pointer; border: 0; padding: 0;
  background: var(--pc-face, #1f6b55); color: #fff; font: 11px/26px system-ui, sans-serif; text-align: center; box-shadow: 0 3px 10px rgb(0 0 0 / .25); }
.pc-play[hidden] { display: none; }
.pc-play:focus-visible { outline: 2px solid var(--pc-face-ring, #44a785); outline-offset: 2px; }
.pc-layer.pc-left .pc-heard { right: auto; left: ${EDGE}px; border-radius: 16px 16px 16px 4px; }
.pc-layer.pc-left .pc-calling { right: auto; left: calc(${EDGE}px + var(--pc-dot-size, ${SIZE}px) + 8px); flex-direction: row-reverse; }
.pc-layer.pc-left.pc-away .pc-calling { left: ${EDGE}px; }
.pc-spot { position: fixed; border-radius: 16px; box-shadow: 0 0 0 9999px rgb(10 18 16 / .34), 0 0 0 3px var(--pc-face-ring, #44a785); opacity: 0; transition: opacity .3s; }
.pc-spot.pc-on { opacity: 1; }
.pc-ring { position: fixed; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%; border: 2px solid var(--pc-face-ring, #44a785); opacity: 0; }
.pc-ring.pc-go { animation: pc-ring 1.1s ease-out 2; }
@keyframes pc-ring { 0% { transform: scale(.6); opacity: .9; } 100% { transform: scale(3.2); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .pc-face, .pc-bubble, .pc-heard, .pc-spot { transition: none; } .pc-ring.pc-go { animation: none; opacity: .9; } }
`;

/** Which side of the tip the face and its words sit on: to its left or right, above or below it. */
export interface Side {
  west: boolean;
  up: boolean;
}

/** How far the face and its words reach from the tip, across and down, in px; above, they end this far over it. */
const REACH = { across: 340, down: 96, over: 14 };
/** How much of the box being explained the face may touch: the tip stands in its first line. */
const TOUCH = 6;
const SIDES: readonly Side[] = [
  { west: false, up: false },
  { west: true, up: false },
  { west: false, up: true },
  { west: true, up: true },
];

/** The first side whose reach fits the screen and covers nothing of `avoid`; else the first that fits; else below and right. */
export function sideOf(tip: Point, avoid: DOMRect | null, width: number, height: number): Side {
  const reach = (side: Side): { left: number; right: number; top: number; bottom: number } => ({
    left: side.west ? tip.x - REACH.across : tip.x + 8,
    right: side.west ? tip.x - 8 : tip.x + REACH.across,
    top: side.up ? tip.y - REACH.down : tip.y + 8,
    bottom: side.up ? tip.y - REACH.over : tip.y + REACH.down,
  });
  const fits = (side: Side): boolean => {
    const box = reach(side);
    return box.left >= 0 && box.right <= width && box.top >= 0 && box.bottom <= height;
  };
  const clear = (side: Side): boolean => {
    const box = reach(side);
    if (avoid === null) return true;
    return box.right <= avoid.left + TOUCH || box.left >= avoid.right - TOUCH || box.bottom <= avoid.top + TOUCH || box.top >= avoid.bottom - TOUCH;
  };
  return SIDES.find((side) => fits(side) && clear(side)) ?? SIDES.find(fits) ?? { west: false, up: false };
}

export interface PersonOptions {
  /** The corner it rests in. */
  dock: "right" | "left";
  /** What the face is called for a screen reader: "Talk to Pip". */
  label: string;
  /** The face's and the arrow's colour, any CSS colour; the page's `--pc-face` when left out. */
  color?: string | undefined;
  /** A click (or Enter) on the face. */
  onClick: () => void;
  /** The hang-up button: its name, and its click. */
  hangUp: { label: string; onClick: () => void };
  /** The button that stops a walk: its name, and its click. */
  stop: { label: string; onClick: () => void };
  /** The button that holds a walk and goes on with it: its name, and its click. */
  pause: { label: string; onClick: () => void };
  /** The buttons that take a walk a sentence back, and on to the next. */
  back: { label: string; onClick: () => void };
  next: { label: string; onClick: () => void };
  /** The captions button, when the site lets the visitor choose: its name, and its click. */
  captions: { label: string; onClick: () => void } | null;
  /** The ▶ beside an element the site wrote a line for: its name, and its click with that element. */
  explain: { label: string; onClick: (element: Element) => void };
}

export class Person {
  /** The element the face is drawn into. */
  readonly face: HTMLElement;
  readonly #document: Document;
  readonly #style: HTMLStyleElement;
  readonly #layer: HTMLElement;
  readonly #person: HTMLElement;
  readonly #arrow: SVGElement;
  readonly #bubble: HTMLElement;
  readonly #heard: HTMLElement;
  readonly #calling: HTMLElement;
  readonly #cc: HTMLElement;
  readonly #stop: HTMLElement;
  readonly #pause: HTMLElement;
  readonly #back: HTMLElement;
  readonly #next: HTMLElement;
  readonly #hang: HTMLElement;
  readonly #play: HTMLElement;
  #offered: Element | null = null;
  readonly #spot: HTMLElement;
  readonly #ring: HTMLElement;
  readonly #dock: "right" | "left";
  #at: Point;
  #shown = "";
  #heardShown = "";

  constructor(document: Document, options: PersonOptions) {
    this.#document = document;
    this.#dock = options.dock;
    this.#style = document.createElement("style");
    this.#style.textContent = STYLE;
    this.#layer = document.createElement("div");
    this.#layer.className = "pc-layer";
    this.#layer.dataset["pinecallSkip"] = "";
    if (options.color !== undefined) this.#layer.style.setProperty("--pc-face", options.color);
    this.#layer.innerHTML = `<div class="pc-spot"></div><div class="pc-ring"></div><div class="pc-person">${ARROW}<svg class="pc-progress" viewBox="0 0 100 100" hidden aria-hidden="true"><circle cx="50" cy="50" r="47" pathLength="100" stroke-dasharray="0 100"></circle></svg><div class="pc-face" role="button" tabindex="0"></div><div class="pc-bubble" role="status" hidden></div></div><div class="pc-heard" role="status" hidden></div><div class="pc-calling" hidden><button type="button" class="pc-back" hidden>${BACK}</button><button type="button" class="pc-pause" aria-pressed="false" hidden>${PAUSE}</button><button type="button" class="pc-next" hidden>${NEXT}</button><button type="button" class="pc-stop" hidden>${STOP}</button><button type="button" class="pc-cc" aria-pressed="true">${CAPTIONS(15)}</button><button type="button" class="pc-hang">✕</button></div><button type="button" class="pc-play" hidden>▶</button>`;
    this.#spot = this.#part(".pc-spot");
    this.#ring = this.#part(".pc-ring");
    this.#person = this.#part(".pc-person");
    this.#arrow = this.#part<SVGElement>(".pc-arrow");
    this.face = this.#part(".pc-face");
    this.#bubble = this.#part(".pc-bubble");
    this.#heard = this.#part(".pc-heard");
    this.#calling = this.#part(".pc-calling");
    this.#cc = this.#part(".pc-cc");
    this.#stop = this.#button(".pc-stop", options.stop);
    this.#pause = this.#button(".pc-pause", options.pause);
    this.#back = this.#button(".pc-back", options.back);
    this.#next = this.#button(".pc-next", options.next);
    this.#play = this.#part(".pc-play");
    this.#play.setAttribute("aria-label", options.explain.label);
    this.#play.title = options.explain.label;
    this.#play.addEventListener("click", () => {
      if (this.#offered !== null) options.explain.onClick(this.#offered);
    });
    this.#person.classList.toggle("pc-left", options.dock === "left");
    this.#layer.classList.toggle("pc-left", options.dock === "left");
    this.#hang = this.#part(".pc-hang");
    this.#hang.setAttribute("aria-label", options.hangUp.label);
    this.#hang.title = options.hangUp.label;
    this.#hang.addEventListener("click", options.hangUp.onClick);
    this.#cc.hidden = options.captions === null;
    if (options.captions !== null) {
      this.#cc.setAttribute("aria-label", options.captions.label);
      this.#cc.title = options.captions.label;
      this.#cc.addEventListener("click", options.captions.onClick);
    }
    this.face.setAttribute("aria-label", options.label);
    this.face.title = options.label;
    this.face.addEventListener("click", options.onClick);
    this.face.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      options.onClick();
    });
    document.head.append(this.#style);
    document.body.append(this.#layer);
    this.#at = this.dock();
    this.place(this.#at);
  }

  /** Where the face rests: its middle, its edge a few px in from the corner. */
  dock(): Point {
    const view = this.#document.defaultView;
    const width = view?.innerWidth ?? 0;
    const height = view?.innerHeight ?? 0;
    const inset = EDGE + this.radius;
    return { x: this.#dock === "right" ? width - inset : inset, y: height - inset };
  }

  /** The tip, now. */
  get at(): Point {
    return this.#at;
  }

  /**
   * Put the tip at a point of the viewport, the face and its words on `side`, or on the side of it that
   * fits the screen and covers nothing of `avoid`, the box being explained: right or left, below or above.
   */
  place(point: Point, avoid: DOMRect | null = null, side?: Side): void {
    this.#at = point;
    this.#person.style.transform = `translate(${point.x.toFixed(1)}px, ${point.y.toFixed(1)}px)`;
    const view = this.#document.defaultView;
    side ??= sideOf(point, avoid, view?.innerWidth ?? 0, view?.innerHeight ?? 0);
    this.#person.classList.toggle("pc-west", side.west);
    this.#person.classList.toggle("pc-up", side.up);
  }


  /** Out of the corner with the arrow showing, the buttons sliding into it; or back in it, and they aside. */
  tour(on: boolean): void {
    this.#person.classList.toggle("pc-touring", on);
    this.#layer.classList.toggle("pc-away", on);
  }

  get touring(): boolean {
    return this.#person.classList.contains("pc-touring");
  }

  kind(kind: Kind): void {
    this.#arrow.dataset["kind"] = kind;
  }

  /** What it is saying: the words said, and the ones still to come; null hides the bubble. */
  say(lit: string | null, coming = ""): void {
    const shown = lit === null ? "" : `${lit}\u0000${coming}`;
    if (shown === this.#shown) return;
    this.#shown = shown;
    this.#bubble.hidden = lit === null;
    if (lit === null) return;
    const later = this.#document.createElement("span");
    later.className = "pc-coming";
    later.textContent = coming;
    this.#bubble.replaceChildren(this.#document.createTextNode(lit), later);
  }

  /** What the visitor is saying, in the corner; null hides it. */
  heard(text: string | null): void {
    if ((text ?? "") === this.#heardShown) return;
    this.#heardShown = text ?? "";
    this.#heard.hidden = text === null;
    if (text !== null) this.#heard.textContent = text;
  }

  /**
   * The corner's buttons: captions and hang-up while a call is on, back, pause, next, stop and captions
   * while a walk plays; captions pressed while they show, pause while the walk is held. Called every frame, so
   * it writes only what changed.
   */
  buttons(call: boolean, walk: boolean, captioned: boolean, paused = false): void {
    const show = (element: HTMLElement, on: boolean): void => {
      if (element.hidden === on) element.hidden = !on;
    };
    show(this.#calling, call || walk);
    show(this.#hang, call);
    for (const one of [this.#back, this.#pause, this.#next, this.#stop]) show(one, walk && !call);
    const press = (element: HTMLElement, on: boolean): void => {
      if (element.getAttribute("aria-pressed") !== String(on)) element.setAttribute("aria-pressed", String(on));
    };
    press(this.#cc, captioned);
    press(this.#pause, paused);
  }

  /** The ▶ at the top right of `element`, or none. Called every frame while shown, so it follows the element. */
  offer(element: Element | null): void {
    this.#offered = element;
    this.#play.hidden = element === null;
    if (element === null) return;
    const box = element.getBoundingClientRect();
    const width = this.#document.defaultView?.innerWidth ?? 0;
    this.#play.style.left = `${Math.min(box.right - 34, width - 40).toFixed(0)}px`;
    this.#play.style.top = `${Math.max(box.top + 8, 8).toFixed(0)}px`;
  }

  /** The spotlight on an element's box, or off. Called every frame while on, so it follows the element. */
  spot(element: Element | null): void {
    this.#spot.classList.toggle("pc-on", element !== null);
    if (element === null) return;
    const box = element.getBoundingClientRect();
    const pad = 8;
    const radius = Number.parseFloat(this.#document.defaultView?.getComputedStyle(element).borderRadius ?? "") || 10;
    Object.assign(this.#spot.style, {
      left: `${box.left - pad}px`,
      top: `${box.top - pad}px`,
      width: `${box.width + pad * 2}px`,
      height: `${box.height + pad * 2}px`,
      borderRadius: `${radius + pad}px`,
    });
  }

  /** "Here": a ring where the tip is, twice. */
  ring(): void {
    this.#ring.style.left = `${this.#at.x}px`;
    this.#ring.style.top = `${this.#at.y}px`;
    this.#ring.classList.remove("pc-go");
    void this.#ring.offsetWidth;
    this.#ring.classList.add("pc-go");
  }

  /** Put another part on the person's layer, out of what the agent reads: the walks' button and pills. */
  add(element: Element): void {
    this.#layer.append(element);
  }

  /**
   * Half the resting face's width, in px, touring or not: read off a face still small from a walk, it
   * set the walks' button where the face, grown back, covered it.
   */
  get radius(): number {
    const size = Number.parseFloat(this.#document.defaultView?.getComputedStyle(this.face).getPropertyValue("--pc-dot-size") ?? "");
    return (Number.isFinite(size) && size > 0 ? size : SIZE) / 2;
  }

  /** How far a walk has played, 0 to 1, as a ring round the face; null takes the ring away. */
  progress(fraction: number | null): void {
    const ring = this.#part<SVGElement>(".pc-progress");
    ring.toggleAttribute("hidden", fraction === null);
    const done = Math.round(Math.min(1, Math.max(0, fraction ?? 0)) * 1000) / 10;
    ring.querySelector("circle")?.setAttribute("stroke-dasharray", `${done} ${100 - done}`);
  }

  close(): void {
    this.#layer.remove();
    this.#style.remove();
  }

  /** A button of the corner, named and wired. */
  #button(selector: string, action: { label: string; onClick: () => void }): HTMLElement {
    const button = this.#part(selector);
    button.setAttribute("aria-label", action.label);
    button.title = action.label;
    button.addEventListener("click", action.onClick);
    return button;
  }

  #part<T extends Element = HTMLElement>(selector: string): T {
    const found = this.#layer.querySelector<T & Element>(selector);
    if (found === null) throw new Error(`the person has no ${selector}`);
    return found;
  }
}
