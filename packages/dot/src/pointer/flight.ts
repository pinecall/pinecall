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
  const e = minJerk(u);
  if (distance < 1) return { x: from.x + dx * e, y: from.y + dy * e };
  const lift = Math.sin(Math.PI * e) * Math.min(60, distance * 0.12);
  return { x: from.x + dx * e - (dy / distance) * lift, y: from.y + dy * e + (dx / distance) * lift };
}

/** Where a person aims on an element: the middle of its first words (at most 60 px in), else the middle of its box. */
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
      const words = range.getBoundingClientRect();
      if (words.width > 0) return { x: words.left + Math.min(words.width / 2, 60), y: words.top + words.height / 2 };
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

/** Scroll the page, eased, until the element sits at `where` of the screen's height. Nothing when it is there already. */
export async function scrollOnto(element: Element, where: number, still: boolean): Promise<void> {
  const view = element.ownerDocument.defaultView;
  if (view === null) return;
  const box = element.getBoundingClientRect();
  const most = element.ownerDocument.documentElement.scrollHeight - view.innerHeight;
  const goal = Math.max(0, Math.min(most, view.scrollY + box.top + box.height / 2 - view.innerHeight * where));
  const from = view.scrollY;
  const dy = goal - from;
  if (Math.abs(dy) < 8) return;
  const ms = still ? 0 : Math.round(520 + 680 * Math.min(1, Math.abs(dy) / (view.innerHeight * 2)));
  await animate(ms, (u) => view.scrollTo(0, from + dy * minJerk(u)));
}
