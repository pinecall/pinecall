/** A page read aloud with no call: what the site marks `data-pinecall-read`, part by part, in the agent's voice, the part read lit and pointed at; its examples pressed on the way. */
//
// The site marks a container `data-pinecall-read`: its headings, paragraphs, items and captions are read
// in the page's order, as written. Each is recorded in the agent's voice when the reading reaches it, by
// the site's door (`{ read }`), the next one asked for while one plays; a part longer than the voice takes
// at once is read a few sentences at a time. A button marked `data-pinecall-press` in it is an example:
// pressed when the reading reaches it (its value, when it has one, said first), and the reading waits for
// what the button controls (`aria-controls`) to answer and not be busy, then says its `data-pinecall-then`
// (what the output shows) pointing at it, and each note of its `data-pinecall-notes` list pointing at the
// line of the output the note finds (`data-pinecall-find`): the output lit line by line, as a person
// reads a result with a finger on it. A button marked `data-pinecall-explain` with no notes of its own
// has its output explained by the site's door (`{ explain }`, the agent's model) once it answered, the
// notes it gives read the same way, in the place of its `data-pinecall-then` (said when the model gives none). Under `data-pinecall-quiet` nothing is read (code, a legend),
// though a button marked to press there is still pressed. An element with `data-pinecall-say` is said
// as that line, written to be heard, instead of what it shows; the parts inside it are not read again. A heading that
// shares its box with one text alone (a card: its title and its words) is read with it, "Title. Words",
// and the whole box lit: a title said alone, then its words, sounds like two things.

import type { ExplainRequest, Note } from "../wire/ask.js";
import type { RecordedStep, RecordedWalk, WalkStep } from "../wire/index.js";
import type { Acting } from "./acting.js";

export const READ_ATTRIBUTE = "data-pinecall-read";
export const PRESS_ATTRIBUTE = "data-pinecall-press";
export const QUIET_ATTRIBUTE = "data-pinecall-quiet";
/** The line an element is said as, instead of what it shows: the same the agent says in a call. */
export const SAY_ATTRIBUTE = "data-pinecall-say";
/** What an example's output shows, said pointing at it once it answered. */
export const THEN_ATTRIBUTE = "data-pinecall-then";
/** On an example's button: the id of a list of notes on its output, each `data-pinecall-find` a text (or `/a regex/`) of a line of it. */
export const NOTES_ATTRIBUTE = "data-pinecall-notes";
export const FIND_ATTRIBUTE = "data-pinecall-find";
/** On an example's button: its output, when no note of the page's covers it, explained by the site's door; its value names the command. */
export const EXPLAIN_ATTRIBUTE = "data-pinecall-explain";
/** On an output while its notes are read, for the site to widen it: a box that scrolls shows whole. */
export const READING_ATTRIBUTE = "data-pinecall-reading";
/** The name a page read aloud plays under. */
export const READ_WALK = "read";

/** The parts of a container a person reads out, each once: the outermost when one holds another. */
const PARTS = "h1, h2, h3, h4, h5, h6, p, li, dt, dd, figcaption, blockquote, caption";
/** The most characters one recording takes: a few sentences. */
const LONGEST = 480;

/** A step about an example's output: the output, and the text of the line it is about; null, the output whole. */
export interface AboutOutput {
  output: Element;
  find: string | null;
}

/** A page as it is read: its steps, the element each step is about, and which are about an output. */
export interface Reading {
  walk: RecordedWalk;
  at: Element[];
  outputs: (AboutOutput | undefined)[];
}

const INLINE = new Set(["SPAN", "CODE", "B", "I", "EM", "STRONG", "A", "SMALL", "KBD", "U", "S", "MARK", "TIME", "SUB", "SUP", "ABBR"]);

/** The nearest box of `element`, within `within`, that is a line of its own: not a run of words (a span, a code) inside one. */
function blockOf(element: Element, within: Element): Element {
  let node = element;
  while (node !== within && node.parentElement !== null) {
    const display = node.ownerDocument.defaultView?.getComputedStyle(node).display ?? "";
    if (!INLINE.has(node.tagName) && !display.startsWith("inline") && display !== "contents") return node;
    node = node.parentElement;
  }
  return node;
}

/** What an output shows, line by line: each box of its own on a line, the words inside it as written. Hidden parts left out. */
export function textOf(output: Element): string {
  const lines: string[] = [];
  const walk = (node: Node, line: string[]): void => {
    for (const child of node.childNodes) {
      if (child instanceof Text) line.push(child.textContent ?? "");
      else if (child instanceof Element && seen(child) && !child.matches("script, style, template")) {
        // A span laid out as a block (a cell of a row) is a line of its own; one in a run of words is not.
        const display = child.ownerDocument.defaultView?.getComputedStyle(child).display ?? "";
        const inline = display === "" ? INLINE.has(child.tagName) : display.startsWith("inline");
        if (inline) walk(child, line);
        else {
          const own: string[] = [];
          walk(child, own);
          lines.push(own.join("").replace(/\s+/g, " ").trim());
        }
      }
    }
  };
  const top: string[] = [];
  walk(output, top);
  const first = top.join("").replace(/\s+/g, " ").trim();
  return [first, ...lines].filter((line) => line !== "").join("\n");
}

/** A text as two are compared for a note: one space between words, in lower case. */
const flat = (text: string): string => text.replace(/\s+/g, " ").trim().toLowerCase();

/** The line of `output` that holds `find`, a text in any case and spacing or `/a regex/flags`: the innermost box that holds it; null when none does. */
export function lineIn(output: Element, find: string): Element | null {
  const expr = /^\/(.+)\/([a-z]*)$/.exec(find);
  let matches: (text: string) => boolean;
  try {
    const regex = expr === null ? null : new RegExp(expr[1] ?? "", (expr[2] ?? "").replace("g", ""));
    const wanted = flat(find);
    matches = regex === null ? (text) => flat(text).includes(wanted) : (text) => regex.test(text);
  } catch {
    return null;
  }
  const holding = [...output.querySelectorAll("*")].filter((element) => matches(element.textContent ?? ""));
  const innermost = holding.find((element) => !holding.some((other) => other !== element && element.contains(other)));
  if (innermost === undefined) return matches(output.textContent ?? "") ? output : null;
  return blockOf(innermost, output);
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
  const outputs: (AboutOutput | undefined)[] = [];
  /** The words of a card, read with its title. */
  const read = new Set<Element>();
  const line = (text: string, element: Element, about?: AboutOutput): void => {
    for (const piece of piecesOf(text.replace(/\s+/g, " ").trim())) {
      steps.push({ say: piece, beats: [], live: true });
      at.push(element);
      outputs[at.length - 1] = about;
    }
  };
  for (const root of roots) {
    for (const element of root.querySelectorAll(`${PARTS}, [${PRESS_ATTRIBUTE}], [${SAY_ATTRIBUTE}]`)) {
      if (!seen(element)) continue;
      if (element.hasAttribute(PRESS_ATTRIBUTE)) {
        line(element.getAttribute(PRESS_ATTRIBUTE) ?? "", element);
        steps.push({ press: element.getAttribute("aria-label") ?? wordsOf(element) });
        at.push(element);
        const controls = element.getAttribute("aria-controls");
        const output = (controls === null ? null : document.getElementById(controls)) ?? element;
        line(element.getAttribute(THEN_ATTRIBUTE) ?? "", output, { output, find: null });
        // Each note on the output, said pointing at the line it finds; one that finds none is left out as it is reached.
        const notes = element.getAttribute(NOTES_ATTRIBUTE);
        for (const note of (notes === null ? null : document.getElementById(notes))?.children ?? []) {
          const find = note.getAttribute(FIND_ATTRIBUTE);
          if (find !== null && find !== "") line(note.textContent ?? "", output, { output, find });
        }
        continue;
      }
      // Inside a part said as its own line, nothing is read again; quiet, nothing at all.
      const told = element.parentElement?.closest(`[${SAY_ATTRIBUTE}]`) ?? null;
      if ((told !== null && root.contains(told)) || element.closest(`[${QUIET_ATTRIBUTE}]`) !== null) continue;
      if (element.hasAttribute(SAY_ATTRIBUTE)) {
        line(element.getAttribute(SAY_ATTRIBUTE) ?? "", element);
        continue;
      }
      // A part inside another part of the same container is read with it.
      const holder = element.parentElement?.closest(PARTS) ?? null;
      if ((holder !== null && root.contains(holder)) || read.has(element)) continue;
      const together = card(element, root);
      if (together !== null) read.add(together.words);
      line(together?.text ?? wordsOf(element), together?.box ?? element);
    }
  }
  return steps.length === 0 ? null : { walk: { name: READ_WALK, title, steps }, at, outputs };
}

/** What reading a page takes from the tutor. */
export interface ReadingOptions {
  /** A text recorded in the agent's voice, by the site's door; null when it was not. */
  record: (text: string) => Promise<RecordedStep | null>;
  /** The part being read lit and pointed at, the rest dimmed; null puts the light out. */
  light: (element: Element | null) => void;
  /** An example pressed, and what it controls waited on until it answered. */
  press: (element: Element) => Promise<void>;
  /** An output explained by the site's door: notes on its lines; none when the door gives none. */
  explain?: ((request: ExplainRequest) => Promise<Note[]>) | undefined;
}

/** One reading under way: each part recorded when it is reached, the next one asked for while one plays. */
export class ReadAloud {
  readonly reading: Reading;
  readonly #options: ReadingOptions;
  readonly #asked = new Map<number, Promise<RecordedStep | null>>();
  /** The output whose notes are being read, marked for the site to widen it. */
  #open: Element | null = null;

  constructor(reading: Reading, options: ReadingOptions) {
    this.reading = reading;
    this.#options = options;
  }

  /** The `at`th step recorded, and the next sentence asked for, so it is there when this one ends; a note whose line is not in the output, none. */
  voice(at: number): Promise<RecordedStep | null> {
    const about = this.reading.outputs[at];
    if (about !== undefined && about.find !== null && lineIn(about.output, about.find) === null) return Promise.resolve(null);
    const recording = this.#record(at);
    const next = this.reading.walk.steps.findIndex((step, index) => index > at && "live" in step);
    if (next !== -1) void this.#record(next);
    return recording;
  }

  /** The `at`th step, an example: pressed, waited on, and its output explained by the door when the page notes nothing on it. */
  async act(at: number): Promise<void> {
    const element = this.reading.at[at];
    if (element === undefined) return;
    this.#options.light(element);
    await this.#options.press(element);
    const command = element.getAttribute(EXPLAIN_ATTRIBUTE);
    // Its own output, by what it controls: a press the page says nothing after has no step about it.
    const controls = element.getAttribute("aria-controls");
    const output = (controls === null ? null : element.ownerDocument.getElementById(controls)) ?? element;
    const noted = this.reading.outputs.some((about) => about !== undefined && about.output === output && about.find !== null);
    if (command === null || this.#options.explain === undefined || noted) return;
    const text = textOf(output);
    if (text === "") return;
    const notes = await this.#options.explain({ output: text, command: command || undefined, language: output.ownerDocument.documentElement.lang || undefined }).catch(() => []);
    const { steps } = this.reading.walk;
    const { at: where, outputs } = this.reading;
    // The model's notes take the place of the page's line on the output (`then`): both would say what it shows. The
    // page's stays when the model gave none.
    if (notes.length > 0) {
      for (let index = outputs.length - 1; index > at; index -= 1) {
        if (outputs[index]?.output !== output || outputs[index]?.find !== null) continue;
        steps.splice(index, 1);
        where.splice(index, 1);
        outputs.splice(index, 1);
      }
    }
    for (const [offset, note] of notes.entries()) {
      steps.splice(at + 1 + offset, 0, { say: note.say, beats: [], live: true });
      where.splice(at + 1 + offset, 0, output);
      outputs.splice(at + 1 + offset, 0, { output, find: note.find });
    }
    // What was asked for ahead stands on the old numbering: asked again where the steps moved.
    for (const index of [...this.#asked.keys()]) if (index > at) this.#asked.delete(index);
  }

  /** The `at`th step starts: its part lit and pointed at, an output's line by its note; -1, the reading is over. */
  shows(at: number): void {
    const about = at < 0 ? undefined : this.reading.outputs[at];
    const output = about?.output ?? null;
    if (this.#open !== output) {
      this.#open?.removeAttribute(READING_ATTRIBUTE);
      output?.setAttribute(READING_ATTRIBUTE, "");
      this.#open = output;
    }
    const element = at < 0 ? null : (this.reading.at[at] ?? null);
    this.#options.light(about === undefined || about.find === null ? element : (lineIn(about.output, about.find) ?? element));
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
    explain: (request) => acting.explain(request),
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
