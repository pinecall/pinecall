/** The walks beside the resting face, with no call: the button and its pills, the player, the code a step shows, and what the next call is told was played. */

import type { Face } from "../face/index.js";
import { CodeWindow } from "../pointer/code.js";
import { Sections } from "../pointer/sections.js";
import { Menu } from "../pointer/menu.js";
import type { Person } from "../pointer/person.js";
import type { RecordedWalk } from "../wire/index.js";
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
}

export class Walks {
  /** The window of code a step opens; a call's macro steps open it too. */
  readonly code: CodeWindow;
  readonly #walking: Walking;
  readonly #menu: Menu;
  readonly #sections: Sections;
  readonly #drawn: Face;
  readonly #person: Person;
  readonly #options: WalksOptions;
  #list: RecordedWalk[] = [];
  #played: Walked | null = null;

  constructor(document: Document, person: Person, drawn: Face, options: WalksOptions) {
    this.#person = person;
    this.#drawn = drawn;
    this.#options = options;
    this.code = new CodeWindow(document, (part) => person.add(part), options.still);
    this.#walking = new Walking(document.createElement("audio"), (walked) => this.#ended(walked), (step) => {
      // A step that names no code keeps the window as it is; the walk's end closes it.
      if (step === null) return this.code.hide();
      const lit = this.code.show(step.code, step.lines);
      if (lit !== null) options.point(lit);
    });
    this.#menu = new Menu(document, (part) => person.add(part), {
      dock: options.dock,
      label: options.label,
      more: options.more,
      face: () => ({ at: person.dock(), radius: person.radius }),
      onPick: (index) => this.#play(index),
    });
    const named = (name: string): number => this.#list.findIndex((walk) => walk.name === name);
    this.#sections = new Sections(document, {
      onReach: (name) => this.#menu.suggest(named(name)),
      onPlay: (name) => this.#play(named(name)),
    });
    void publishedWalks(options.url ?? "").then((found) => {
      this.#list = found;
      this.#menu.offer(found.map((walk) => ({ title: walk.title, ms: lengthOf(walk) })));
      this.#sections.offer(found.map((walk) => walk.name));
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
    this.code.close();
  }

  #play(index: number): void {
    const walk = this.#list[index];
    if (walk === undefined || this.#options.inCall()) return;
    this.#drawn.wake();
    this.#drawn.listen(this.#walking.audio);
    this.#menu.available(false);
    this.#walking.start(walk);
    this.#options.onWalk?.({ walk: walk.name, step: 1, of: walk.steps.length, done: false });
  }

  #ended(walked: Walked): void {
    this.#played = walked;
    this.#drawn.listen(null);
    this.#person.progress(null);
    this.code.hide();
    this.#options.home();
    this.#menu.available(!this.#options.inCall());
    this.#options.onWalk?.(walked);
  }
}
