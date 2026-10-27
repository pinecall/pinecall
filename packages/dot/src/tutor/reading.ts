/** A page read aloud with no call: what the site marks `data-pinecall-read`, part by part, in the agent's voice, the part read lit and pointed at; its examples pressed on the way. */
//
// The site marks a container `data-pinecall-read`: its headings, paragraphs, items and captions are read
// in the page's order, as written. Each is recorded in the agent's voice when the reading reaches it, by
// the site's door (`{ read }`), the next one asked for while one plays; a part longer than the voice takes
// at once is read a few sentences at a time. A field marked `data-pinecall-type` is an example the page
// types: its value is typed into it when the reading reaches it, and the button marked `data-pinecall-press`
// after it sends it, in any form (the page's own example, not the visitor's). A button marked
// `data-pinecall-press` in it is an example:
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
// and the whole box lit: a title said alone, then its words, sounds like two things. A frame of the site's own
// (a chat, a widget) is read in its place, as a page: what its page marks `data-pinecall-read`. A send button
// marked `data-pinecall-goal` is a chat the dot talks to: it asks the door for its line, says it, types and sends
// it, reads the agent's answer aloud (`data-pinecall-said` on each turn), and goes on until it has what it came
// for, then has the whole chat explained. A page read with its top scrolled away is read from the first part
// still in view (`fromHere`): a person who comes back to the middle of a chapter goes on from there.

import { boxOf, pageOf } from "../pointer/frames.js";
import { seenOf } from "../pointer/flight.js";
import { notPressable } from "../pointer/pressing.js";
import { MOST_HEARD, type ExplainRequest, type Heard, type NextLine, type NextRequest, type Note } from "../wire/ask.js";
import type { RecordedStep, RecordedWalk, WalkStep } from "../wire/index.js";
import type { Acting } from "./acting.js";
import { QUIET_ATTRIBUTE, lineIn, piecesOf, seen, textOf, wordsOf } from "./text.js";

export { QUIET_ATTRIBUTE, lineIn, piecesOf, textOf, wordsOf } from "./text.js";

export const READ_ATTRIBUTE = "data-pinecall-read";
export const PRESS_ATTRIBUTE = "data-pinecall-press";
/** On a field: the words typed into it when the reading reaches it, the page's own example (a chat's question); the `data-pinecall-press` after it sends it. */
export const TYPE_ATTRIBUTE = "data-pinecall-type";
/** On a chat's send button: the dot talks to what it sends to, turn by turn, until it gets this (or the chat ends), then has the talk explained. */
export const GOAL_ATTRIBUTE = "data-pinecall-goal";
/** On each turn of a chat talked to: whose it is, `agent` or `caller`; the agent's are read aloud as they come. */
export const SAID_ATTRIBUTE = "data-pinecall-said";
/** The most turns of its own a talk takes: the gateway's own ceiling on a caller's, whatever the goal. */
const MOST_TURNS = 40;
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

/** A step about an example's output: the output, and the text of the line it is about; null, the output whole. */
export interface AboutOutput {
  output: Element;
  find: string | null;
}

/** A step added as a reading goes: the step, the element it is about, and the output it is about. */
type Added = [WalkStep, Element, AboutOutput | undefined];

/** A page as it is read: its steps, the element each step is about, which are about an output, and the goal a step talks for. */
export interface Reading {
  walk: RecordedWalk;
  at: Element[];
  outputs: (AboutOutput | undefined)[];
  goals: WeakMap<WalkStep, string>;
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

/** The containers of `document` that are read, outermost. */
function rootsOf(document: Document): Element[] {
  return [...document.querySelectorAll(`[${READ_ATTRIBUTE}]`)].filter((root) => root.parentElement?.closest(`[${READ_ATTRIBUTE}]`) == null);
}

/** The page as it reads now, under the title the menu shows it with; null when it marks nothing to read. */
export function readingOf(document: Document, title: string): Reading | null {
  const steps: WalkStep[] = [];
  const at: Element[] = [];
  const outputs: (AboutOutput | undefined)[] = [];
  const goals = new WeakMap<WalkStep, string>();
  /** The words of a card, read with its title. */
  const read = new Set<Element>();
  const line = (text: string, element: Element, about?: AboutOutput): void => {
    for (const piece of piecesOf(text.replace(/\s+/g, " ").trim())) {
      steps.push({ say: piece, beats: [], live: true });
      at.push(element);
      outputs[at.length - 1] = about;
    }
  };
  const scan = (root: Element): void => {
    for (const element of root.querySelectorAll(`${PARTS}, [${PRESS_ATTRIBUTE}], [${TYPE_ATTRIBUTE}], [${SAY_ATTRIBUTE}], iframe`)) {
      if (!seen(element)) continue;
      // A frame of the site's own is read in its place, as a page is: what its page marks.
      if (element.tagName === "IFRAME") {
        const page = pageOf(element);
        if (page !== null) rootsOf(page).forEach(scan);
        continue;
      }
      if (element.hasAttribute(TYPE_ATTRIBUTE)) {
        steps.push({ fill: labelOf(element), with: element.getAttribute(TYPE_ATTRIBUTE) ?? "" });
        at.push(element);
        continue;
      }
      if (element.hasAttribute(PRESS_ATTRIBUTE)) {
        line(element.getAttribute(PRESS_ATTRIBUTE) ?? "", element);
        const press: WalkStep = { press: labelOf(element) };
        steps.push(press);
        at.push(element);
        // A button with a goal: the dot talks to what it sends to when it reaches it (`ReadAloud`); nothing is said of it before.
        const goal = element.getAttribute(GOAL_ATTRIBUTE);
        if (goal !== null && goal !== "") {
          goals.set(press, goal);
          continue;
        }
        const output = outputOf(element);
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
  };
  rootsOf(document).forEach(scan);
  return steps.length === 0 ? null : { walk: { name: READ_WALK, title, steps }, at, outputs, goals };
}

/** How far above what is seen a part may start and still be where the reading begins, in px. */
const JUST_ABOVE = 8;

/** The reading from where the page is scrolled to: from its first part not above what is seen; whole when that is its first. */
export function fromHere(reading: Reading): Reading {
  const first = reading.at.findIndex((element) => boxOf(element).bottom > seenOf(element).top + JUST_ABOVE);
  if (first <= 0) return reading;
  return { walk: { ...reading.walk, steps: reading.walk.steps.slice(first) }, at: reading.at.slice(first), outputs: reading.outputs.slice(first), goals: reading.goals };
}

/** The name a step calls an example by: its label, its placeholder, its words. */
const labelOf = (element: Element): string => element.getAttribute("aria-label") ?? element.getAttribute("placeholder") ?? wordsOf(element) ?? "field";

/** An example's output: what it controls (`aria-controls`), else itself. */
function outputOf(element: Element): Element {
  const controls = element.getAttribute("aria-controls");
  return (controls === null ? null : element.ownerDocument.getElementById(controls)) ?? element;
}

/** The language an output's page is in, for the door; none when the page does not say. */
const languageOf = (element: Element): string | undefined => element.ownerDocument.documentElement.lang || undefined;

/** What reading a page takes from the tutor. */
export interface ReadingOptions {
  /** A text recorded in the agent's voice, by the site's door; null when it was not. */
  record: (text: string) => Promise<RecordedStep | null>;
  /** The part being read lit and pointed at, the rest dimmed; null puts the light out. */
  light: (element: Element | null) => void;
  /** An example pressed, and what it controls waited on until it answered. */
  press: (element: Element) => Promise<void>;
  /** The page's own example typed into a field, the pointer on it. */
  type?: ((element: Element, text: string) => Promise<void>) | undefined;
  /** An output explained by the site's door: notes on its lines; none when the door gives none. */
  explain?: ((request: ExplainRequest) => Promise<Note[]>) | undefined;
  /** The dot's next line on a chat it talks to for a goal, by the site's door; null when it gives none. */
  next?: ((request: NextRequest) => Promise<NextLine | null>) | undefined;
}

/** One reading under way: each part recorded when it is reached, the next one asked for while one plays. */
export class ReadAloud {
  readonly reading: Reading;
  readonly #options: ReadingOptions;
  readonly #asked = new Map<number, Promise<RecordedStep | null>>();
  /** The output whose notes are being read, marked for the site to widen it. */
  #open: Element | null = null;
  /** The agent's answers read aloud already, on a chat talked to. */
  readonly #heard = new WeakSet<Element>();
  /** The chats the dot said goodbye on. */
  readonly #bye = new WeakSet<Element>();
  /** The presses of a talk's turns: the talk is explained at its end, not turn by turn. */
  readonly #turns = new WeakSet<WalkStep>();

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

  /** The `at`th step, an example: typed into a field; a turn of a talk; or pressed, waited on, and its output explained by the door when the page notes nothing on it. */
  async act(at: number): Promise<void> {
    const element = this.reading.at[at];
    const step = this.reading.walk.steps[at];
    if (element === undefined || step === undefined) return;
    const goal = this.reading.goals.get(step);
    if (goal !== undefined) return this.#talk(at, element, goal);
    this.#options.light(element);
    if ("fill" in step) {
      await this.#options.type?.(element, step.with);
      return;
    }
    await this.#options.press(element);
    if (this.#turns.has(step)) return;
    // Its own output, by what it controls: a press the page says nothing after has no step about it.
    const output = outputOf(element);
    const noted = this.reading.outputs.some((about) => about !== undefined && about.output === output && about.find !== null);
    if (!noted) await this.#explain(at, output, element.getAttribute(EXPLAIN_ATTRIBUTE));
  }

  /** The output explained by the door: its notes after step `at`, in the place of the page's line on it (kept when the model gave none). */
  async #explain(at: number, output: Element, command: string | null): Promise<void> {
    if (command === null || this.#options.explain === undefined) return;
    const text = textOf(output);
    if (text === "") return;
    const notes = await this.#options.explain({ output: text, command: command || undefined, language: languageOf(output) }).catch(() => []);
    const { steps } = this.reading.walk;
    const { at: where, outputs } = this.reading;
    if (notes.length > 0) {
      for (let index = outputs.length - 1; index > at; index -= 1) {
        if (outputs[index]?.output !== output || outputs[index]?.find !== null) continue;
        steps.splice(index, 1);
        where.splice(index, 1);
        outputs.splice(index, 1);
      }
    }
    this.#insert(at, notes.map((note): Added => [{ say: note.say, beats: [], live: true }, output, { output, find: note.find }]));
  }

  /**
   * One turn of a talk, at the step that marks it: the agent's last answer read aloud first, pointing at it; then the
   * dot's next line asked of the door, said, typed and sent, and the turn after it marked. The talk ends when the dot
   * said goodbye, the chat ended, the door gives no line or the turns run out: the whole chat is then explained.
   */
  async #talk(at: number, button: Element, goal: string): Promise<void> {
    const output = outputOf(button);
    const field = button.closest("form")?.querySelector("input:not([type=hidden]), textarea") ?? null;
    const turns = [...output.querySelectorAll(`[${SAID_ATTRIBUTE}]`)].filter(seen);
    const marker = (): Added => {
      const step: WalkStep = { press: labelOf(button) };
      this.reading.goals.set(step, goal);
      return [step, button, undefined];
    };
    const say = (text: string, element: Element): Added[] => piecesOf(text).map((piece) => [{ say: piece, beats: [], live: true }, element, undefined]);
    const last = turns.at(-1);
    if (last !== undefined && last.getAttribute(SAID_ATTRIBUTE) === "agent" && !this.#heard.has(last)) {
      this.#heard.add(last);
      this.#insert(at, [...say(wordsOf(last), last), marker()]);
      return;
    }
    const heard = turns.map((turn): Heard => ({ who: turn.getAttribute(SAID_ATTRIBUTE) === "agent" ? "agent" : "caller", said: wordsOf(turn) })).slice(-MOST_HEARD);
    const mine = heard.filter((turn) => turn.who === "caller").length;
    const over = field === null || notPressable(button, true) !== null || this.#bye.has(output) || mine >= MOST_TURNS;
    const next = over || this.#options.next === undefined ? null : await this.#options.next({ goal, heard, language: languageOf(output) }).catch(() => null);
    if (next === null || field === null) return this.#explain(at, output, button.getAttribute(EXPLAIN_ATTRIBUTE) ?? goal);
    if (next.hangup) this.#bye.add(output);
    const press: WalkStep = { press: labelOf(button) };
    this.#turns.add(press);
    this.#insert(at, [...say(next.say, field), [{ fill: labelOf(field), with: next.say }, field, undefined], [press, button, undefined], marker()]);
  }

  /** Steps put after the `at`th; what was asked for ahead stands on the old numbering, so it is asked again. */
  #insert(at: number, added: Added[]): void {
    const { steps } = this.reading.walk;
    const { at: where, outputs } = this.reading;
    for (const [offset, [step, element, about]] of added.entries()) {
      steps.splice(at + 1 + offset, 0, step);
      where.splice(at + 1 + offset, 0, element);
      outputs.splice(at + 1 + offset, 0, about);
    }
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
  moves: { light: (element: Element | null) => void; queued: <T>(work: () => Promise<T>) => Promise<T> },
): { title: string } & ReadingOptions {
  return {
    title,
    record: (text) => acting.read(text),
    explain: (request) => acting.explain(request),
    next: (request) => acting.next(request),
    light: moves.light,
    type: (element, text) => moves.queued(async () => void (await acting.type(element, text))),
    // The page's own example: its button pressed in any form.
    press: (element) =>
      moves.queued(async () => {
        if ((await acting.press(element, true)) !== null) return;
        // What it controls is on its own page: a chat in a frame of the site's own answers there.
        const controls = element.getAttribute("aria-controls");
        const output = controls === null ? null : element.ownerDocument.getElementById(controls);
        if (output !== null) await acting.wait(() => output, EXAMPLE_MS);
      }),
  };
}
