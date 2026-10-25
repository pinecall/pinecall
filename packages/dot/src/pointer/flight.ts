/** How the pointer moves: where it aims on an element, the path it flies, and the page scrolled like a hand scrolls it. */
//
// The path is the screen recorder's: minimum jerk, timed by the distance, with a slight arc off the
// straight line, the way a hand moves a mouse.

export interface Point {
  x: number;
  y: number;
}

/** Minimum jerk: 0 to 1, starting and ending still. */
export function minJerk(u: number): number {
  return u * u * u * (10 + u * (-15 + 6 * u));
}

/** How long a flight of `distance` px takes on a screen `width` px wide, in ms. */
export function flightMs(distance: number, width: number): number {
  return Math.round(480 + 560 * Math.min(1, distance / Math.max(1, width)));
}

/** The point at `u` (0 to 1) of the flight from `from` to `to`, bent a little off the line. */
export function along(from: Point, to: Point, u: number): Point {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.hypot(dx, dy);
  if (u >= 1) return { ...to };
  const e = minJerk(u);
  if (distance < 1) return { x: from.x + dx * e, y: from.y + dy * e };
  const lift = Math.sin(Math.PI * e) * Math.min(60, distance * 0.12);
  return { x: from.x + dx * e - (dy / distance) * lift, y: from.y + dy * e + (dx / distance) * lift };
}

/** How far under the words the tip stands, in px. */
const UNDER = 3;

/**
 * Where a person aims on an element: just under its first line of words, at their middle (at most
 * 60 px in), so the pointer shows the words rather than covering them; else the middle of its box.
 */
export function aimOf(element: Element): Point {
  if (!element.matches("article, section, form, figure, img")) {
    const document = element.ownerDocument;
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => ((node.textContent ?? "").trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP),
    });
    const text = walker.nextNode();
    if (text !== null) {
      const range = document.createRange();
      range.selectNodeContents(text);
      const words = range.getClientRects()[0] ?? range.getBoundingClientRect();
      if (words.width > 0) return { x: words.left + Math.min(words.width / 2, 60), y: words.bottom + UNDER };
    }
  }
  const box = element.getBoundingClientRect();
  return { x: box.left + box.width / 2, y: box.top + Math.min(box.height / 2, 60) };
}

/** Run `step(u)` from 0 to 1 over `ms`, once a frame; resolves at 1. */
export function animate(ms: number, step: (u: number) => void): Promise<void> {
  const start = performance.now();
  return new Promise((done) => {
    const frame = (now: number): void => {
      const u = ms <= 0 ? 1 : Math.min(1, (now - start) / ms);
      step(u);
      if (u < 1) requestAnimationFrame(frame);
      else done();
    };
    requestAnimationFrame(frame);
  });
}

/** How much of the screen's height an element may take and still be centred; a taller one shows its start. */
const TALL = 0.8;
/** Where a tall element's start stands, as a share of the screen's height. */
const START = 0.1;

/**
 * The scroll at which `box` (as the screen shows it at `scrollY`) sits at `where` of the part of a screen
 * `height` tall that the site's own header leaves free (`covered` px at its top), within a page
 * `pageHeight` tall: its middle there, or, for one taller than most of it (a section on a phone), its
 * start near the top of it, so what it begins with is what shows, and nothing hides it.
 */
export function scrollGoal(box: { top: number; height: number }, scrollY: number, height: number, pageHeight: number, where: number, covered = 0): number {
  const free = height - covered;
  const at = box.height > free * TALL ? box.top - covered - free * START : box.top + box.height / 2 - covered - free * where;
  return Math.max(0, Math.min(pageHeight - height, scrollY + at));
}

/** The most of the screen's top a site's bar may cover and still count as a header, as a share of the screen's height. */
const A_HEADER = 0.4;

/**
 * How much of the screen's top the site itself covers, in px: its `scroll-padding-top` when it says, and
 * the bottom of any fixed or sticky bar along the top edge (a header), whichever is lower. The tutor's own
 * layer does not count.
 */
export function coveredTop(document: Document): number {
  const view = document.defaultView;
  if (view === null) return 0;
  const padding = Number.parseFloat(view.getComputedStyle(document.documentElement).scrollPaddingTop);
  let covered = Number.isFinite(padding) ? padding : 0;
  const most = view.innerHeight * A_HEADER;
  for (const x of [0.25, 0.5, 0.75].map((share) => view.innerWidth * share)) {
    for (const hit of document.elementsFromPoint?.(x, 1) ?? []) {
      for (let node: Element | null = hit; node !== null; node = node.parentElement) {
        if (node.closest("[data-pinecall-skip]") !== null) break;
        const position = view.getComputedStyle(node).position;
        if (position !== "fixed" && position !== "sticky") continue;
        const box = node.getBoundingClientRect();
        if (box.top <= 1 && box.height < most) covered = Math.max(covered, box.bottom);
      }
    }
  }
  return Math.min(covered, most);
}

/** Scroll the page, eased, until the element sits at `where` of the screen's height. Nothing when it is there already. */
export async function scrollOnto(element: Element, where: number, still: boolean): Promise<void> {
  const view = element.ownerDocument.defaultView;
  if (view === null) return;
  const box = element.getBoundingClientRect();
  const goal = scrollGoal(box, view.scrollY, view.innerHeight, element.ownerDocument.documentElement.scrollHeight, where, coveredTop(element.ownerDocument));
  const from = view.scrollY;
  const dy = goal - from;
  if (Math.abs(dy) < 8) return;
  const ms = still ? 0 : Math.round(520 + 680 * Math.min(1, Math.abs(dy) / (view.innerHeight * 2)));
  await animate(ms, (u) => view.scrollTo(0, from + dy * minJerk(u)));
}
