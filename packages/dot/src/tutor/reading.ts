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
// marked `data-pinecall-goal` is a chat the dot talks to: it asks the door for its line, says it as it types it
// (the letters paced to the recording), sends it, reads the agent's answer aloud (`data-pinecall-said` on each turn), and goes on until it has what it came
// for, then has the whole chat explained. Any chat's answer (`data-pinecall-said="agent"`) is read as it came
// once the press that drew it out is done, before the notes on it. A page read with its top scrolled away is read from the first part
// still in view (`fromHere`): a person who comes back to the middle of a chapter goes on from there.

import { boxOf, frameOf, pageOf } from "../pointer/frames.js";
import { seenOf } from "../pointer/flight.js";
import type { RecordedWalk, WalkStep } from "../wire/index.js";
import { QUIET_ATTRIBUTE, piecesOf, seen, wordsOf } from "./text.js";

export { QUIET_ATTRIBUTE, lineIn, piecesOf, textOf, wordsOf } from "./text.js";

export const READ_ATTRIBUTE = "data-pinecall-read";
export const PRESS_ATTRIBUTE = "data-pinecall-press";
/** On a field: the words typed into it when the reading reaches it, the page's own example (a chat's question); the `data-pinecall-press` after it sends it. */
export const TYPE_ATTRIBUTE = "data-pinecall-type";
/** On a chat's send button: the dot talks to what it sends to, turn by turn, until it gets this (or the chat ends), then has the talk explained. */
export const GOAL_ATTRIBUTE = "data-pinecall-goal";
/** On each turn of a chat talked to: whose it is, `agent`, `caller` or another (a tool the agent used); all but the caller's read aloud as they come, by their `data-pinecall-say` when they have one. */
export const SAID_ATTRIBUTE = "data-pinecall-said";
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

/** Words typed into a field as a sentence is said. */
export interface Typed {
  field: Element;
  text: string;
}

/** A page as it is read: its steps, the element each is about, which are about an output, the goal a step talks for, and what is typed as one is said. */
export interface Reading {
  walk: RecordedWalk;
  at: Element[];
  outputs: (AboutOutput | undefined)[];
  goals: WeakMap<WalkStep, string>;
  typed: WeakMap<WalkStep, Typed>;
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
  const typed = new WeakMap<WalkStep, Typed>();
  /** A field marked to type, typed as the next press's line is said. */
  let pending: Typed | null = null;
  /** The words of a card, read with its title. */
  const read = new Set<Element>();
  const line = (text: string, element: Element, about?: AboutOutput): WalkStep[] => {
    const said: WalkStep[] = [];
    for (const piece of piecesOf(text.replace(/\s+/g, " ").trim())) {
      const step: WalkStep = { say: piece, beats: [], live: true };
      steps.push(step);
      said.push(step);
      at.push(element);
      outputs[at.length - 1] = about;
    }
    return said;
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
        pending = { field: element, text: element.getAttribute(TYPE_ATTRIBUTE) ?? "" };
        continue;
      }
      if (element.hasAttribute(PRESS_ATTRIBUTE)) {
        const goal = element.getAttribute(GOAL_ATTRIBUTE);
        // Its line is said pointing at the field typed in meanwhile; a chat's, at the chat itself; else at the button.
        const shown = pending?.field ?? (goal ? (frameOf(element.ownerDocument) ?? outputOf(element)) : element);
        const said = line(element.getAttribute(PRESS_ATTRIBUTE) ?? "", shown);
        if (pending !== null) {
          // Typed as the line is said; with no line to say, typed on its own.
          if (said[0] !== undefined) typed.set(said[0], pending);
          else {
            steps.push({ fill: labelOf(pending.field), with: pending.text });
            at.push(pending.field);
          }
          pending = null;
        }
        const press: WalkStep = { press: labelOf(element) };
        steps.push(press);
        at.push(element);
        // A button with a goal: the dot talks to what it sends to when it reaches it (`ReadAloud`); nothing is said of it before.
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
      // A chat's turns (a tool's line among them) are read as the dot talks to it, not as the page.
      if (element.closest(`[${SAID_ATTRIBUTE}]`) !== null) continue;
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
  return steps.length === 0 ? null : { walk: { name: READ_WALK, title, steps }, at, outputs, goals, typed };
}

/** How far above what is seen a part may start and still be where the reading begins, in px. */
const JUST_ABOVE = 8;

/** The reading from where the page is scrolled to: from its first part not above what is seen; whole when that is its first. */
export function fromHere(reading: Reading): Reading {
  const first = reading.at.findIndex((element) => boxOf(element).bottom > seenOf(element).top + JUST_ABOVE);
  if (first <= 0) return reading;
  return { ...reading, walk: { ...reading.walk, steps: reading.walk.steps.slice(first) }, at: reading.at.slice(first), outputs: reading.outputs.slice(first) };
}

/** The name a step calls an example by: its label, its placeholder, its words. */
export const labelOf = (element: Element): string => element.getAttribute("aria-label") ?? element.getAttribute("placeholder") ?? wordsOf(element) ?? "field";

/** An example's output: what it controls (`aria-controls`), else itself. */
export function outputOf(element: Element): Element {
  const controls = element.getAttribute("aria-controls");
  return (controls === null ? null : element.ownerDocument.getElementById(controls)) ?? element;
}

/** The language an output's page is in, for the door; none when the page does not say. */
export const languageOf = (element: Element): string | undefined => element.ownerDocument.documentElement.lang || undefined;
