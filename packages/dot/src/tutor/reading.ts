/** A page read aloud with no call: what the site marks `data-pinecall-read`, part by part, in the agent's voice, the part read lit and pointed at; its examples pressed on the way. */
//
// The site marks a container `data-pinecall-read`: its headings, paragraphs, items and captions are read
// in the page's order, as written. Each is recorded in the agent's voice when the reading reaches it, by
// the site's door (`{ read }`), the next one asked for while one plays; a part longer than the voice takes
// at once is read a few sentences at a time. A button marked `data-pinecall-press` in it is an example:
// pressed when the reading reaches it (its value, when it has one, said first), and the reading waits for
// what the button controls (`aria-controls`) to answer and not be busy. Under `data-pinecall-quiet` nothing
// is read (code, a legend), though a button marked to press there is still pressed. A heading that
// shares its box with one text alone (a card: its title and its words) is read with it, "Title. Words",
// and the whole box lit: a title said alone, then its words, sounds like two things.

import type { RecordedStep, RecordedWalk, WalkStep } from "../wire/index.js";
import type { Acting } from "./acting.js";

export const READ_ATTRIBUTE = "data-pinecall-read";
export const PRESS_ATTRIBUTE = "data-pinecall-press";
export const QUIET_ATTRIBUTE = "data-pinecall-quiet";
/** The name a page read aloud plays under. */
export const READ_WALK = "read";

/** The parts of a container a person reads out, each once: the outermost when one holds another. */
const PARTS = "h1, h2, h3, h4, h5, h6, p, li, dt, dd, figcaption, blockquote, caption";
/** The most characters one recording takes: a few sentences. */
const LONGEST = 480;

/** A page as it is read: its steps, and the element each step is about. */
export interface Reading {
  walk: RecordedWalk;
  at: Element[];
}

/** Whether a person sees `element`: not hidden, not left out for the tutor. */
function seen(element: Element): boolean {
  if (element.closest("[hidden], [aria-hidden='true'], [data-pinecall-skip]") !== null) return false;
  const style = element.ownerDocument.defaultView?.getComputedStyle(element);
  return style === undefined || (style.display !== "none" && style.visibility !== "hidden");
}

/** The words a person reads out of `element`, on one line: its text, without what is quiet or hidden inside it. */
export function wordsOf(element: Element): string {
  const document = element.ownerDocument;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let text = "";
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (parent === null || parent.closest(`[${QUIET_ATTRIBUTE}]`) !== null || !seen(parent) || parent.matches("script, style, template")) continue;
    text += node.textContent ?? "";
  }
  return text.replace(/\s+/g, " ").trim();
}

/** A text as it is recorded: whole when it fits, else a few sentences at a time, `longest` characters at most each. */
export function piecesOf(text: string, longest = LONGEST): string[] {
  if (text.length <= longest) return text === "" ? [] : [text];
  const sentences = text.split(/(?<=[.!?…:;])\s+/);
  const pieces: string[] = [];
  let piece = "";
  for (const sentence of sentences.flatMap((one) => (one.length <= longest ? [one] : cut(one, longest)))) {
    if (piece !== "" && piece.length + 1 + sentence.length > longest) {
      pieces.push(piece);
      piece = sentence;
    } else piece = piece === "" ? sentence : `${piece} ${sentence}`;
  }
  if (piece !== "") pieces.push(piece);
  return pieces;
}

/** A sentence longer than a recording, cut between its words. */
function cut(sentence: string, longest: number): string[] {
  const pieces: string[] = [];
  let piece = "";
  for (const word of sentence.split(" ")) {
    if (piece !== "" && piece.length + 1 + word.length > longest) {
      pieces.push(piece);
      piece = word;
    } else piece = piece === "" ? word : `${piece} ${word}`;
  }
  return piece === "" ? pieces : [...pieces, piece];
}

/** The parts of `box` a person reads, outermost, in order. */
function partsIn(box: Element): Element[] {
  return [...box.querySelectorAll(PARTS)].filter((part) => seen(part) && part.closest(`[${QUIET_ATTRIBUTE}]`) === null && !box.contains(part.parentElement?.closest(PARTS) ?? null));
}

/** A heading and the one text it shares its box with, as one: the box and "Title. Words"; null when it is not one. */
function card(heading: Element, root: Element): { box: Element; text: string; words: Element } | null {
  const box = heading.parentElement;
  if (box === null || box === root || !root.contains(box) || !/^H[1-6]$/.test(heading.tagName)) return null;
  const parts = partsIn(box);
  const words = parts[1];
  if (parts.length !== 2 || parts[0] !== heading || words === undefined) return null;
  const title = wordsOf(heading);
  return { box, words, text: `${title}${/[.!?:…]$/.test(title) ? "" : "."} ${wordsOf(words)}` };
}

/** The page as it reads now, under the title the menu shows it with; null when it marks nothing to read. */
export function readingOf(document: Document, title: string): Reading | null {
  const roots = [...document.querySelectorAll(`[${READ_ATTRIBUTE}]`)].filter((root) => root.parentElement?.closest(`[${READ_ATTRIBUTE}]`) == null);
  const steps: WalkStep[] = [];
  const at: Element[] = [];
  /** The words of a card, read with its title. */
  const read = new Set<Element>();
  for (const root of roots) {
    for (const element of root.querySelectorAll(`${PARTS}, [${PRESS_ATTRIBUTE}]`)) {
      if (!seen(element)) continue;
      if (element.hasAttribute(PRESS_ATTRIBUTE)) {
        const first = element.getAttribute(PRESS_ATTRIBUTE)?.trim() ?? "";
        if (first !== "") {
          steps.push({ say: first, beats: [], live: true });
          at.push(element);
        }
        steps.push({ press: element.getAttribute("aria-label") ?? wordsOf(element) });
        at.push(element);
        continue;
      }
      // A part inside another part of the same container is read with it.
      const holder = element.parentElement?.closest(PARTS) ?? null;
      if ((holder !== null && root.contains(holder)) || element.closest(`[${QUIET_ATTRIBUTE}]`) !== null || read.has(element)) continue;
      const together = card(element, root);
      if (together !== null) read.add(together.words);
      for (const piece of piecesOf(together?.text ?? wordsOf(element))) {
        steps.push({ say: piece, beats: [], live: true });
        at.push(together?.box ?? element);
      }
    }
  }
  return steps.length === 0 ? null : { walk: { name: READ_WALK, title, steps }, at };
}

/** What reading a page takes from the tutor. */
export interface ReadingOptions {
  /** A text recorded in the agent's voice, by the site's door; null when it was not. */
  record: (text: string) => Promise<RecordedStep | null>;
  /** The part being read lit and pointed at, the rest dimmed; null puts the light out. */
  light: (element: Element | null) => void;
  /** An example pressed, and what it controls waited on until it answered. */
  press: (element: Element) => Promise<void>;
}

/** One reading under way: each part recorded when it is reached, the next one asked for while one plays. */
export class ReadAloud {
  readonly reading: Reading;
  readonly #options: ReadingOptions;
  readonly #asked = new Map<number, Promise<RecordedStep | null>>();

  constructor(reading: Reading, options: ReadingOptions) {
    this.reading = reading;
    this.#options = options;
  }

  /** The `at`th step recorded, and the next sentence asked for, so it is there when this one ends. */
  voice(at: number): Promise<RecordedStep | null> {
    const recording = this.#record(at);
    const next = this.reading.walk.steps.findIndex((step, index) => index > at && "live" in step);
    if (next !== -1) void this.#record(next);
    return recording;
  }

  /** The `at`th step, an example: pressed, and waited on. */
  async act(at: number): Promise<void> {
    const element = this.reading.at[at];
    if (element === undefined) return;
    this.#options.light(element);
    await this.#options.press(element);
  }

  /** The `at`th step starts: its part lit and pointed at; -1, the reading is over. */
  shows(at: number): void {
    this.#options.light(at < 0 ? null : (this.reading.at[at] ?? null));
  }

  #record(at: number): Promise<RecordedStep | null> {
    const step = this.reading.walk.steps[at];
    if (step === undefined || !("live" in step)) return Promise.resolve(null);
    let recording = this.#asked.get(at);
    if (recording === undefined) {
      recording = this.#options.record(step.say).catch(() => null);
      this.#asked.set(at, recording);
    }
    return recording;
  }
}

/** How long a reading waits for an example it pressed to answer, in ms. */
const EXAMPLE_MS = 60_000;

/**
 * What a reading takes, from the tutor's acts and moves: each part recorded by the site's door, the part read
 * lit and pointed at (`light`), and an example pressed, then what it controls (its output) waited on until it
 * answered and is not busy.
 */
export function readingWith(
  title: string,
  acting: Acting,
  document: Document,
  moves: { light: (element: Element | null) => void; queued: <T>(work: () => Promise<T>) => Promise<T> },
): { title: string } & ReadingOptions {
  return {
    title,
    record: (text) => acting.read(text),
    light: moves.light,
    press: (element) =>
      moves.queued(async () => {
        if ((await acting.press(element)) !== null) return;
        const controls = element.getAttribute("aria-controls");
        const output = controls === null ? null : document.getElementById(controls);
        if (output !== null) await acting.wait(() => output, EXAMPLE_MS);
      }),
  };
}
