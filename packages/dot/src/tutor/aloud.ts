/** One reading under way: each part recorded as it is reached, the examples pressed, typed and talked to, the outputs explained; and what a reading takes from the tutor. */

import { notPressable } from "../pointer/pressing.js";
import { MOST_HEARD, type ExplainRequest, type Heard, type NextLine, type NextRequest, type Note } from "../wire/ask.js";
import type { RecordedStep, WalkStep } from "../wire/index.js";
import type { Acting } from "./acting.js";
import { EXPLAIN_ATTRIBUTE, HEARD_ATTRIBUTE, READING_ATTRIBUTE, SAID_ATTRIBUTE, SAY_ATTRIBUTE, SAYING_EVENT, labelOf, languageOf, outputOf, type AboutOutput, type Reading } from "./reading.js";
import { lineIn, piecesOf, seen, textOf, wordsOf } from "./text.js";

/** The most turns of its own a talk takes: the gateway's own ceiling on a caller's, whatever the goal. */
const MOST_TURNS = 40;

/** A step added as a reading goes: the step, the element it is about, and the output it is about. */
type Added = [WalkStep, Element, AboutOutput | undefined];

/** What reading a page takes from the tutor. */
export interface ReadingOptions {
  /** A text recorded in the agent's voice, by the site's door; null when it was not. */
  record: (text: string) => Promise<RecordedStep | null>;
  /** The part being read lit and pointed at, the rest dimmed; null puts the light out. */
  light: (element: Element | null) => void;
  /** An example pressed, and what it controls waited on until it answered. */
  press: (element: Element) => Promise<void>;
  /** The page's own example typed into a field, the pointer on it; paced to `ms`, the recording said meanwhile. */
  type?: ((element: Element, text: string, ms?: number) => Promise<void>) | undefined;
  /** An output explained by the site's door: notes on its lines; none when the door gives none. */
  explain?: ((request: ExplainRequest) => Promise<Note[]>) | undefined;
  /** The dot's next line on a chat it talks to for a goal, by the site's door; null when it gives none. */
  next?: ((request: NextRequest) => Promise<NextLine | null>) | undefined;
  /** A chat talked to opened before its first line: its field focused, and its output waited on while it says it is busy (a greeting coming). */
  open?: ((field: Element, output: Element) => Promise<void>) | undefined;
  /** A spoken call's output waited on while it says it is busy: the agent answering what the dot said into it. */
  settle?: ((output: Element) => Promise<void>) | undefined;
}

/** One reading under way: each part recorded when it is reached, the next one asked for while one plays. */
export class ReadAloud {
  readonly reading: Reading;
  readonly #options: ReadingOptions;
  readonly #asked = new Map<number, Promise<RecordedStep | null>>();
  /** The output whose notes are being read, marked for the site to widen it. */
  #open: Element | null = null;
  /** The chats talked to that were opened already. */
  readonly #opened = new WeakSet<Element>();
  /** The agent's answers read aloud already, on a chat talked to. */
  readonly #heard = new WeakSet<Element>();
  /** The chats the dot said goodbye on. */
  readonly #bye = new WeakSet<Element>();
  /** The presses of a talk's turns: read as the talk goes, never explained after. */
  readonly #turns = new WeakSet<WalkStep>();
  /** Each step's recording, once recorded: what a typing is paced to, and what a call is told. */
  readonly #recorded = new Map<number, RecordedStep>();
  /** The steps whose typing, or telling, started. */
  readonly #begun = new WeakSet<WalkStep>();

  constructor(reading: Reading, options: ReadingOptions) {
    this.reading = reading;
    this.#options = options;
  }

  /** The `at`th step recorded, and the next sentence asked for, so it is there when this one ends; a note whose line is not in the output, none. */
  voice(at: number): Promise<RecordedStep | null> {
    const about = this.reading.outputs[at];
    if (about !== undefined && about.find !== null && lineIn(about.output, about.find) === null) return Promise.resolve(null);
    const recording = this.#record(at).then((step) => {
      if (step !== null) this.#recorded.set(at, step);
      return step;
    });
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
    // What the agent answered in a chat is read as it came, pointing at it, before anything is said of it.
    let after = at;
    for (const turn of this.#unheard(output)) {
      const said = this.#say(turn.getAttribute(SAY_ATTRIBUTE) ?? wordsOf(turn), turn);
      this.#insert(after, said);
      after += said.length;
    }
    const noted = this.reading.outputs.some((about) => about !== undefined && about.output === output && about.find !== null);
    if (!noted) await this.#explain(after, output, element.getAttribute(EXPLAIN_ATTRIBUTE));
  }

  /** The turns of a chat not read aloud yet, in order, the agent's and the tools it used: all but the caller's; each counted as read. On a spoken call the agent is heard, not read: its turns are counted and left out. */
  #unheard(output: Element): Element[] {
    const turns = [...output.querySelectorAll(`[${SAID_ATTRIBUTE}]:not([${SAID_ATTRIBUTE}="caller"])`)].filter((turn) => seen(turn) && !this.#heard.has(turn));
    for (const turn of turns) this.#heard.add(turn);
    return output.hasAttribute(HEARD_ATTRIBUTE) ? turns.filter((turn) => turn.getAttribute(SAID_ATTRIBUTE) !== "agent") : turns;
  }

  /** A text said pointing at `element`, a recording at a time. */
  #say(text: string, element: Element): Added[] {
    return piecesOf(text).map((piece) => [{ say: piece, beats: [], live: true }, element, undefined]);
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
   * One turn of a talk, at the step that marks it: the chat opened first, if it was not; what the agent said since
   * (and the tools it used) read aloud, pointing at each; then the dot's next line asked of the door, said, typed
   * and sent, and the turn after it marked. A button in no form is a spoken call: the button opens it, the agent is
   * heard and not read, and the dot's lines are said into the call (`SAYING_EVENT`) with nothing to send. The talk
   * ends when the dot said goodbye, the chat ended (a turn marked `end`, a send button disabled), the door gives no
   * line or the turns run out; the page then goes on, the chat having been read as it went.
   */
  async #talk(at: number, button: Element, goal: string): Promise<void> {
    const output = outputOf(button);
    const field = button.closest("form")?.querySelector("input:not([type=hidden]), textarea") ?? null;
    const spoken = field === null;
    if (!this.#opened.has(output)) {
      this.#opened.add(output);
      // A call is opened by its button, its greeting waited on; a chat opens as its field is focused.
      if (spoken) await this.#options.press(button);
      else await this.#options.open?.(field, output);
    } else if (spoken) {
      // The agent answering what was said into the call: waited on while the output says it is busy.
      await this.#options.settle?.(output);
    }
    const marker = (): Added => {
      const step: WalkStep = { press: labelOf(button) };
      this.reading.goals.set(step, goal);
      return [step, button, undefined];
    };
    const unheard = this.#unheard(output);
    if (unheard.length > 0) {
      this.#insert(at, [...unheard.flatMap((turn) => this.#say(turn.getAttribute(SAY_ATTRIBUTE) ?? wordsOf(turn), turn)), marker()]);
      return;
    }
    const turns = [...output.querySelectorAll(`[${SAID_ATTRIBUTE}="agent"], [${SAID_ATTRIBUTE}="caller"]`)].filter(seen);
    const heard = turns.map((turn): Heard => ({ who: turn.getAttribute(SAID_ATTRIBUTE) === "agent" ? "agent" : "caller", said: wordsOf(turn) })).slice(-MOST_HEARD);
    const mine = heard.filter((turn) => turn.who === "caller").length;
    const ended = output.querySelector(`[${SAID_ATTRIBUTE}="end"]`) !== null;
    const over = ended || this.#bye.has(output) || mine >= MOST_TURNS || (field !== null && notPressable(button, true) !== null);
    const next = over || this.#options.next === undefined ? null : await this.#options.next({ goal, heard, language: languageOf(output) }).catch(() => null);
    if (next === null) return;
    if (next.hangup) this.#bye.add(output);
    if (field === null) {
      // Said pointing at the call, and into it: each piece told to the output as it starts playing.
      const said = this.#say(next.say, output);
      for (const [step] of said) this.reading.spoken.set(step, output);
      this.#insert(at, [...said, marker()]);
      return;
    }
    const press: WalkStep = { press: labelOf(button) };
    this.#turns.add(press);
    const said = this.#say(next.say, field);
    if (said[0] !== undefined) this.reading.typed.set(said[0][0], { field, text: next.say });
    this.#insert(at, [...said, [press, button, undefined], marker()]);
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
    for (const index of [...this.#recorded.keys()]) if (index > at) this.#recorded.delete(index);
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
    // A sentence typed as it is said: the typing starts with it, paced to its recording.
    const step = at < 0 ? undefined : this.reading.walk.steps[at];
    const typing = step === undefined ? undefined : this.reading.typed.get(step);
    if (step !== undefined && typing !== undefined && !this.#begun.has(step)) {
      this.#begun.add(step);
      void this.#options.type?.(typing.field, typing.text, this.#recorded.get(at)?.durationMs);
    }
    // A sentence said into a call: the call's page is told it as it starts, with its recording, to play it in.
    const into = step === undefined ? undefined : this.reading.spoken.get(step);
    const recorded = this.#recorded.get(at);
    if (step !== undefined && into !== undefined && recorded !== undefined && !this.#begun.has(step)) {
      this.#begun.add(step);
      const detail = { text: recorded.say, audio: recorded.audio, durationMs: recorded.durationMs };
      into.dispatchEvent(new CustomEvent(SAYING_EVENT, { bubbles: true, detail }));
    }
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

/** Whether `output`, or something in it, says it is busy. */
const isBusy = (output: Element): boolean => output.closest("[aria-busy=true]") !== null || output.querySelector("[aria-busy=true]") !== null;

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
    // Focused, a chat may open and greet: waited on only while it says it is busy.
    open: async (field, output) => {
      await moves.queued(async () => (field as HTMLElement).focus({ preventScroll: true }));
      if (isBusy(output)) await acting.wait(() => output, EXAMPLE_MS);
    },
    // A spoken call's output, busy while the agent answers what was said into it: waited on only then.
    settle: async (output) => {
      if (isBusy(output)) await acting.wait(() => output, EXAMPLE_MS);
    },
    light: moves.light,
    type: (element, text, ms) => moves.queued(async () => void (await acting.type(element, text, ms))),
    // The page's own example: its button pressed in any form. The wait after it holds no move: the pointer and
    // the light go on (a visitor skipping ahead) while the output is waited on.
    press: async (element) => {
      if ((await moves.queued(() => acting.press(element, true))) !== null) return;
      // What it controls is on its own page: a chat in a frame of the site's own answers there.
      const controls = element.getAttribute("aria-controls");
      const output = controls === null ? null : element.ownerDocument.getElementById(controls);
      if (output !== null) await acting.wait(() => output, EXAMPLE_MS);
    },
  };
}
