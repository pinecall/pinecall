/** The walks beside the resting face, with no call: the button and its pills, the player, the code a step shows, and what the next call is told was played. */

import type { Face } from "../face/index.js";
import { Asking } from "../pointer/asking.js";
import { CodeWindow } from "../pointer/code.js";
import { Sections } from "../pointer/sections.js";
import { Menu } from "../pointer/menu.js";
import type { Person } from "../pointer/person.js";
import type { AskRequest } from "../wire/ask.js";
import { onPage, type ActStep, type RecordedStep, type RecordedWalk, type Values } from "../wire/index.js";
import { ReadAloud, readingOf, type ReadingOptions } from "./reading.js";
import { Walking, lengthOf, publishedWalks, type WalkFrame, type Walked } from "./walking.js";

export interface WalksOptions {
  dock: "right" | "left";
  /** The button's name: "Walks". */
  label: string;
  /** The name of the button that shows the next walks: "More walks". */
  more: string;
  /** Where the agent published its walks; none offered without it. */
  url: string | undefined;
  /** Whether a call is opening or on: no walk plays over one. */
  inCall: () => boolean;
  /** Send the pointer back to its corner, after the moves already queued. */
  home: () => void;
  /** A walk started, ended or was stopped. */
  onWalk?: ((walked: Walked) => void) | undefined;
  /** Send the pointer onto an element, after the moves already queued: the lines a step lights. */
  point: (element: Element) => void;
  /** Reduced motion: the code is written in at once. */
  still: boolean;
  /** The field for what the visitor wants shown: its placeholder, and what was typed. None, no field. */
  ask?: { placeholder: string; onAsk: (text: string) => void } | undefined;
  /** A walk's act done on the page, with what the visitor typed: the values it read. */
  act?: ((step: ActStep, values: Values, message: string) => Promise<Values>) | undefined;
  /** A walk's sentence with slots, recorded now. */
  voice?: ((walk: RecordedWalk, at: number, values: Values) => Promise<RecordedStep | null>) | undefined;
  /** The page read aloud, first in the menu under `title`, where the site marks `data-pinecall-read`. None, it is not offered. */
  reading?: ({ title: string } & ReadingOptions) | undefined;
}

export class Walks {
  /** The window of code a step opens; a call's macro steps open it too. */
  readonly code: CodeWindow;
  readonly #walking: Walking;
  readonly #menu: Menu;
  readonly #sections: Sections;
  readonly #asking: Asking | undefined;
  readonly #drawn: Face;
  readonly #person: Person;
  readonly #options: WalksOptions;
  readonly #document: Document;
  #list: RecordedWalk[] = [];
  /** The walks the menu and the sections offer: those that take no params, which are asked for. */
  #picked: RecordedWalk[] = [];
  #played: Walked | null = null;
  /** What the visitor typed for the walk playing; none for one picked. */
  #message = "";
  /** The page being read aloud, while it is. */
  #aloud: ReadAloud | null = null;
  /** Whether the menu offers reading the page, first. */
  #readable = false;

  constructor(document: Document, person: Person, drawn: Face, options: WalksOptions) {
    this.#person = person;
    this.#document = document;
    this.#drawn = drawn;
    this.#options = options;
    this.code = new CodeWindow(document, (part) => person.add(part), options.still);
    this.#walking = new Walking(document.createElement("audio"), (walked) => this.#ended(walked), (step, at) => {
      if (this.#aloud !== null) return this.#aloud.shows(step === null ? -1 : at);
      // A step that names no code keeps the window as it is; the walk's end closes it.
      if (step === null) return this.code.hide();
      const lit = this.code.show(step.code, step.lines);
      if (lit !== null) options.point(lit);
    }, {
      act: async (step, values, at) => {
        if (this.#aloud !== null) return this.#aloud.act(at).then(() => ({}));
        return options.act?.(step, values, this.#message) ?? {};
      },
      voice: (walk, at, values) => (this.#aloud !== null ? this.#aloud.voice(at) : options.voice?.(walk, at, values) ?? Promise.resolve(null)),
    });
    const named = (name: string): number => this.#picked.findIndex((walk) => walk.name === name);
    // What was typed folds the menu away; a line about it opens it again (`offer`).
    const ask = options.ask;
    this.#asking = ask === undefined ? undefined : new Asking(document, (part) => person.add(part), {
      placeholder: ask.placeholder,
      onAsk: (text) => {
        this.#menu.toggle(false);
        ask.onAsk(text);
      },
    });
    this.#menu = new Menu(document, (part) => person.add(part), {
      ask: this.#asking,
      dock: options.dock,
      label: options.label,
      more: options.more,
      face: () => ({ at: person.dock(), radius: person.radius }),
      onPick: (index) => (this.#readable && index === 0 ? this.read() : this.#play(this.#picked[index - this.#offset])),
      current: () => {
        const at = named(this.#sections.current() ?? "");
        return at === -1 ? -1 : at + this.#offset;
      },
    });
    this.#sections = new Sections(document, { onPlay: (name) => this.#play(this.#picked[named(name)]) });
    const path = document.defaultView?.location.pathname ?? "";
    void publishedWalks(options.url ?? "", path).then((all) => {
      // Only the walks for the page the visitor is on: one that names other pages stays out of the menu.
      const found = all.filter((walk) => onPage(walk.pages, path));
      this.#list = found;
      this.#picked = found.filter((walk) => walk.params === undefined);
      const reading = options.reading;
      this.#readable = reading !== undefined && readingOf(document, reading.title) !== null;
      this.#menu.offer([...(this.#readable && reading !== undefined ? [{ title: reading.title, ms: 0 }] : []), ...this.#picked.map((walk) => ({ title: walk.title, ms: lengthOf(walk) }))]);
      this.#sections.offer(this.#picked.map((walk) => walk.name));
      this.#menu.available(!options.inCall());
    });
  }

  /** Where the walk playing is now; null while none plays. */
  frame(): WalkFrame | null {
    return this.#walking.frame();
  }

  get playing(): boolean {
    return this.#walking.playing !== null;
  }

  get paused(): boolean {
    return this.#walking.paused;
  }

  /** Hold the walk playing, or go on with it: the visitor's pause button. */
  pause(): void {
    if (this.#walking.paused) this.#walking.resume();
    else this.#walking.pause();
  }

  /** The section scrolled to offers its walk, and the site's own buttons show, while no call is on and no walk plays. Called every frame. */
  place(): void {
    this.#sections.place(!this.#options.inCall() && !this.playing);
  }

  /** The walks of this page, as the field asks about them, with what each takes. */
  listed(): AskRequest["walks"] {
    return this.#list.map((walk) => ({
      name: walk.name,
      title: walk.title,
      ...(walk.when === undefined ? {} : { when: walk.when }),
      ...(walk.params === undefined ? {} : { params: walk.params }),
    }));
  }

  /** Play a walk of this page, by its name, called with `values`: from what the visitor typed (`message`). */
  playNamed(name: string, values: Values = {}, message = ""): void {
    this.#play(this.#list.find((walk) => walk.name === name), values, message);
  }

  /** Read the page aloud, as it is now: what it marks `data-pinecall-read`. Call it from the visitor's click. */
  read(): void {
    const reading = this.#options.reading;
    const found = reading === undefined ? null : readingOf(this.#document, reading.title);
    if (reading === undefined || found === null || this.#options.inCall()) return;
    this.stop();
    this.#aloud = new ReadAloud(found, reading);
    this.#play(found.walk);
  }

  /** Let a walk play after a wait: from the visitor's submit, before the door answers. */
  unlock(): void {
    this.#walking.unlock();
  }

  /** Open the menu with a line under the field about what was asked, and a button to take it on. */
  offer(text: string, action?: { label: string; onClick: () => void }): void {
    this.#menu.toggle(true);
    this.#asking?.hint(text, action);
  }

  /** Stop the walk playing, if one is: the visitor clicked the face, or a call began. */
  stop(): void {
    const walked = this.#walking.stop();
    if (walked !== null) this.#ended(walked);
  }

  /** Whether the button may show: not during a call, nor while a walk plays. */
  available(on: boolean): void {
    this.#menu.available(on && !this.playing);
  }

  /** The walk played since the last call, once: what the next call is told. */
  taken(): Walked | null {
    const played = this.#played;
    this.#played = null;
    return played;
  }

  close(): void {
    this.#walking.stop();
    this.#menu.close();
    this.#sections.close();
    this.#asking?.close();
    this.code.close();
  }

  #play(walk: RecordedWalk | undefined, values: Values = {}, message = ""): void {
    if (walk === undefined || this.#options.inCall()) return;
    this.#message = message;
    this.#drawn.wake();
    this.#drawn.listen(this.#walking.audio);
    this.#menu.available(false);
    this.#walking.start(walk, values);
    this.#options.onWalk?.({ walk: walk.name, step: 1, of: walk.steps.length, done: false });
  }

  /** How many pills stand before the walks': the page read aloud, when it is offered. */
  get #offset(): number {
    return this.#readable ? 1 : 0;
  }

  #ended(walked: Walked): void {
    this.#aloud = null;
    this.#played = walked;
    this.#drawn.listen(null);
    this.#person.progress(null);
    this.code.hide();
    this.#options.home();
    this.#menu.available(!this.#options.inCall());
    this.#options.onWalk?.(walked);
  }
}
