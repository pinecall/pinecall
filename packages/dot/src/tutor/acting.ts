/** What a walk's acts do on the page with no call: a field filled, a button pressed, the page waited on, a table read; and a sentence with slots recorded. */
//
// Each act runs after the pointer's moves queued before it, as a person does one thing after another.
// A press is watched: a wait after it ends when the thing it waits on has changed and then stayed still a
// moment, and says it is not busy (`aria-busy`): a search answered and drawn. Or at its time. A read takes the rows of a table as a person reads them, by
// its header's words, and the row that best answers what the visitor typed, which the site's door picks;
// with nothing typed, or no answer, the first. A sentence with slots is recorded by the site's door when
// it is reached: the door reads the sentence from the agent's walks, and the page sends only the values.

import type { Page } from "../page/page.js";
import { nameOf } from "../page/roles.js";
import { framesIn, isElement } from "../pointer/frames.js";
import { press } from "../pointer/pressing.js";
import { nextOf, notesOf, rowOf, saidOf, type DoorRequest, type ExplainRequest, type NextLine, type NextRequest, type Note } from "../wire/ask.js";
import { filled, slotsOf, valueOf, type ActStep, type LiveStep, type RecordedStep, type RecordedWalk, type ReadAct, type Values } from "../wire/index.js";

export interface ActingOptions {
  document: Document;
  page: Page;
  /** Run `work` after the moves already queued. */
  queued: <T>(work: () => Promise<T>) => Promise<T>;
  /** The pointer onto an element; called inside the queue. */
  point: (element: Element) => Promise<void>;
  /** The ring at the pointer's tip. */
  ring: () => void;
  /** The visitor's words typed into a field, the pointer on it; called inside the queue. Why it could not, or null. */
  type: (element: Element, text: string) => Promise<string | null>;
  /** The site's door; none, a sentence with slots is left out and the first row read. */
  door?: ((request: DoorRequest) => Promise<unknown>) | undefined;
}

/** How long a wait waits when its step does not say, in ms. */
export const WAIT_MS = 8000;
/** How long the page must stay still after it changed for a wait to end, in ms. */
const QUIET_MS = 300;
const LOOK_MS = 100;
/** The most changes kept between a press and its wait. */
const KEPT = 500;

export class Acting {
  readonly #options: ActingOptions;
  #observer: MutationObserver | null = null;
  /** What changed since the press, and when. */
  #changes: { node: Node; at: number }[] = [];

  constructor(options: ActingOptions) {
    this.#options = options;
  }

  /** One act of a walk, after the moves queued before it: the values a read adds. */
  act(step: ActStep, values: Values, message: string): Promise<Values> {
    return this.#options.queued(async () => {
      if ("fill" in step) {
        const text = filled(step.with, values);
        const field = this.#named(step.fill, ["textbox", "combobox"]);
        if (text !== null && field !== null) await this.#options.type(field, text);
        return {};
      }
      if ("press" in step) {
        const button = this.#named(step.press, ["button"]);
        if (button !== null) await this.press(button);
        return {};
      }
      if ("wait" in step) {
        await this.wait(() => this.#named(step.wait), step.ms ?? WAIT_MS);
        return {};
      }
      return this.#read(step, message);
    });
  }

  /** Press a button, the pointer on it first and a ring as it presses; the page is watched from now. Why it could not, or null. `forms`, a page read aloud's example, pressed in any form. */
  async press(element: Element, forms = false): Promise<string | null> {
    await this.#options.point(element);
    this.#options.ring();
    this.#watch();
    return press(element, forms);
  }

  /** Words typed into a field, the pointer on it: a page read aloud's example. Why it could not, or null. */
  type(element: Element, text: string): Promise<string | null> {
    return this.#options.type(element, text);
  }

  /** Wait for `target` to change, settle and not be busy, `ms` at most: true when it did. */
  wait(target: () => Element | null, ms: number): Promise<boolean> {
    const started = performance.now();
    // A wait with no press before it watches from now.
    if (this.#observer === null) this.#watch();
    const waited = new Promise<boolean>((done) => {
      const look = (): void => {
        const now = performance.now();
        const element = target();
        const changed = element === null ? [] : this.#changes.filter((change) => element.contains(change.node));
        const last = changed.at(-1)?.at ?? 0;
        const busy = element?.closest("[aria-busy=true]") != null || element?.querySelector("[aria-busy=true]") != null;
        if (changed.length > 0 && now - last >= QUIET_MS && !busy) return done(true);
        if (now - started >= ms) return done(false);
        setTimeout(look, LOOK_MS);
      };
      look();
    });
    return waited.finally(() => this.#stop());
  }

  /** A sentence with slots, recorded now by the site's door; null when it cannot be. */
  async voice(path: string, walk: RecordedWalk, at: number, values: Values): Promise<RecordedStep | null> {
    const step = walk.steps[at];
    const door = this.#options.door;
    if (door === undefined || step === undefined || !("live" in step)) return null;
    const live: LiveStep = step;
    const asked = Object.fromEntries(slotsOf(live.say).flatMap((slot) => (values[slot] === undefined ? [] : [[slot, values[slot]]])));
    const said = saidOf(await door({ say: { path, walk: walk.name, step: at, values: asked } }).catch(() => null));
    if (said === null) return null;
    const { live: _live, ...shown } = live;
    return { ...shown, say: said.say, audio: said.audio, durationMs: said.durationMs, words: said.words };
  }

  /** An output explained by the site's door, the agent's model: its notes; none when the door gives none. */
  async explain(request: ExplainRequest): Promise<Note[]> {
    const door = this.#options.door;
    if (door === undefined) return [];
    return notesOf(await door({ explain: request }).catch(() => null));
  }

  /** The dot's next line on a chat it talks to for a goal, by the site's door; null when it gives none. */
  async next(request: NextRequest): Promise<NextLine | null> {
    const door = this.#options.door;
    if (door === undefined) return null;
    return nextOf(await door({ next: request }).catch(() => null));
  }

  /** A text of the page, recorded now by the site's door in the agent's voice; null when it cannot be. */
  async read(text: string): Promise<RecordedStep | null> {
    const door = this.#options.door;
    if (door === undefined) return null;
    const said = saidOf(await door({ read: { text } }).catch(() => null));
    return said === null ? null : { say: said.say, audio: said.audio, durationMs: said.durationMs, words: said.words, beats: [] };
  }

  close(): void {
    this.#stop();
  }

  /** The first thing of one of `roles` the page names so, on the screen or not. */
  #named(name: string, roles?: readonly string[]): Element | null {
    const ref = this.#options.page.named(name, roles);
    return ref === null ? null : this.#options.page.element(ref);
  }

  /** The table the step names, its rows by their header's words, and one row's cells as the step's values. */
  async #read(step: ReadAct, message: string): Promise<Values> {
    const named = this.#named(step.read);
    const table = named === null ? null : named.matches("table") ? named : named.querySelector("table");
    if (table === null) return {};
    const all = [...table.querySelectorAll("tr")];
    const headers = [...(all.find((row) => row.querySelector("td") === null)?.children ?? [])].map((cell) => valueOf(cell.textContent ?? ""));
    const rows = all.filter((row) => row.querySelector("td") !== null);
    if (rows.length === 0) return {};
    const names = rows.map((row) => nameOf(row, "row"));
    let at = 0;
    if (step.row === "best" && message !== "" && this.#options.door !== undefined) {
      at = rowOf(await this.#options.door({ row: { message, rows: names } }).catch(() => null)) ?? 0;
    }
    const row = rows[at] ?? rows[0];
    if (row === undefined) return {};
    const values: Values = { [step.as]: names[at] ?? "" };
    [...row.children].forEach((cell, column) => {
      const header = headers[column];
      if (header !== undefined && header !== "") values[`${step.as}.${header}`] = valueOf(cell.textContent ?? "");
    });
    return values;
  }

  /** Count what changes on the page from now, the tutor's own layer left out. */
  #watch(): void {
    this.#changes = [];
    if (this.#observer !== null) return;
    const ours = (node: Node): boolean => (isElement(node) ? node : node.parentElement)?.closest("[data-pinecall-skip]") != null;
    this.#observer = new MutationObserver((records) => {
      const at = performance.now();
      for (const record of records) if (!ours(record.target)) this.#changes.push({ node: record.target, at });
      this.#changes.splice(0, Math.max(0, this.#changes.length - KEPT));
    });
    // The page, and the pages of the site's own frames in it: a chat in a frame answers there.
    for (const page of [this.#options.document, ...framesIn(this.#options.document)]) {
      this.#observer.observe(page.body, { subtree: true, childList: true, characterData: true, attributes: true });
    }
  }

  #stop(): void {
    this.#observer?.disconnect();
    this.#observer = null;
  }
}
