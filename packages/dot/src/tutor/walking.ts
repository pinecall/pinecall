/** A recorded walk played on the page with no call: its sentences in the agent's voice, their words lit as said, the beats on their words. */
//
// One audio element plays every sentence in turn: Safari lets an element the visitor's click
// started go on to its next source, where a new element would need another click. Each frame
// reads where the audio is, so the words and the pointer follow the sound, whatever the network.
// A walk called with values fills its slots: a step that acts (fill, press, wait, read) is done by
// the page between two sentences, and a sentence with slots is recorded when it is reached. A step
// a slot of which nothing filled, or whose `if` or `unless` says so, is left out.

import { filled, isAct, taken, walksDocument, walksOf, type ActStep, type Beat, type RecordedStep, type RecordedWalk, type Step, type Values, type WalkStep } from "../wire/index.js";
import { Player } from "./macro.js";

/** How far the visitor got: the walk, the sentence reached (from 1), how many it has, and whether it ended. */
export interface Walked {
  walk: string;
  step: number;
  of: number;
  done: boolean;
}

/** One frame of a walk: the sentence's words said and to come, the beats due, how far the whole walk is. */
export interface WalkFrame {
  lit: string;
  coming: string;
  beats: Beat[];
  fraction: number;
}

/** A document's walks, read with no key; null where it is not there or cannot be read. */
async function readWalks(url: string): Promise<RecordedWalk[] | null> {
  try {
    const answer = await fetch(url);
    return answer.ok ? walksOf(await answer.json()) : null;
  } catch {
    return null;
  }
}

/**
 * The walks an agent published for the page at `path`, read with no key; none where the page cannot read them.
 * `url` is the agent's `walks` document, the home's: a page of its own has `walks-<page>` beside it, and is
 * read from there, or from `url` when the agent published none for it (the walks that name no page).
 */
export async function publishedWalks(url: string, path = ""): Promise<RecordedWalk[]> {
  if (url === "") return [];
  const own = walksDocument(path);
  const [base, query = ""] = url.split("?");
  if (own !== "walks" && base !== undefined && base.endsWith("/walks")) {
    const found = await readWalks(`${base.slice(0, -"walks".length)}${own}${query === "" ? "" : `?${query}`}`);
    if (found !== null) return found;
  }
  return (await readWalks(url)) ?? [];
}

/** A walk's length, in ms: its recorded sentences'. */
export function lengthOf(walk: RecordedWalk): number {
  return walk.steps.reduce((total, step) => total + ("durationMs" in step ? step.durationMs : 0), 0);
}

/** What a walk's steps that are not recorded take: the acts done, the sentences with slots recorded. */
export interface WalkHooks {
  /** An act of the walk, done, the `at`th step: the values it read. */
  act: (step: ActStep, values: Values, at: number) => Promise<Values>;
  /** A sentence with slots, recorded now: null when it cannot be. */
  voice: (walk: RecordedWalk, at: number, values: Values) => Promise<RecordedStep | null>;
}

const NO_HOOKS: WalkHooks = { act: async () => ({}), voice: async () => null };

// An audio element is the visitor's to start: one that played inside their click goes on playing
// sources after it, so a walk that starts after a wait (a door asked, a search) plays this first.
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

/** A step's beats with the slots of what they find filled: `["row", "{hit}"]`. A beat whose slot nothing filled is left out. */
function beatsFilled(beats: Beat[], values: Values): Beat[] {
  return beats.flatMap((beat) => {
    if (beat.find === undefined) return [beat];
    const name = filled(beat.find[1], values);
    return name === null ? [] : [{ ...beat, find: [beat.find[0], name] as [string, string] }];
  });
}

export class Walking {
  readonly audio: HTMLAudioElement;
  readonly #ended: (walked: Walked) => void;
  readonly #shows: (step: RecordedStep | null, at: number) => void;
  readonly #player = new Player();
  readonly #hooks: WalkHooks;
  #walk: RecordedWalk | null = null;
  #step = 0;
  #paused = false;
  #values: Values = {};
  /** The sentence playing; null while a step acts or is recorded. */
  #current: RecordedStep | null = null;
  /** A sentence ready while the walk was paused, played on resume. */
  #held: RecordedStep | null = null;
  /** Which run of the walk is on: a stop or a new start ends the one before, mid-act. */
  #run = 0;

  /**
   * Play through `audio`; `ended` hears a walk that played to its end, or failed to play; `shows`
   * hears each sentence as it starts (and which step it is), for what it shows beside the page, and null as the walk stops.
   */
  constructor(audio: HTMLAudioElement, ended: (walked: Walked) => void, shows: (step: RecordedStep | null, at: number) => void = () => undefined, hooks: WalkHooks = NO_HOOKS) {
    this.audio = audio;
    this.#ended = ended;
    this.#shows = shows;
    this.#hooks = hooks;
    // The ear reads the audio through Web Audio, which hears silence from a source fetched without CORS.
    audio.crossOrigin = "anonymous";
    audio.preload = "auto";
    audio.addEventListener("ended", () => this.#next());
    audio.addEventListener("error", () => this.#finish(false));
  }

  /** The walk playing, or null. */
  get playing(): RecordedWalk | null {
    return this.#walk;
  }

  /** Whether the walk playing is paused. */
  get paused(): boolean {
    return this.#paused;
  }

  /** Hold the walk where it is: the voice, and the words and beats that follow it. */
  pause(): void {
    if (this.#walk === null || this.#paused) return;
    this.#paused = true;
    this.audio.pause();
  }

  /** Go on from where it was held. Call it from the visitor's click, as `start`. */
  resume(): void {
    if (this.#walk === null || !this.#paused) return;
    this.#paused = false;
    const held = this.#held;
    this.#held = null;
    if (held !== null) this.#play(held);
    else if (this.#current !== null) this.audio.play().catch(() => this.#finish(false));
  }

  /** Let this element play later, from the visitor's click: a walk that starts after a wait. */
  unlock(): void {
    if (this.#walk !== null) return;
    this.audio.src = SILENCE;
    this.audio.play().catch(() => undefined);
  }

  /** Play a walk from its first sentence, its slots filled from `values`. Call it from the visitor's click, or after `unlock`. */
  start(walk: RecordedWalk, values: Values = {}): void {
    this.#walk = walk;
    this.#step = 0;
    this.#values = { ...values };
    void this.#go();
  }

  /** Where the walk is now; null while none plays. */
  frame(): WalkFrame | null {
    const walk = this.#walk;
    if (walk === null) return null;
    const step = this.#current;
    const before = walk.steps.slice(0, this.#step).reduce((total, one) => total + ("durationMs" in one ? one.durationMs : 0), 0);
    const fraction = Math.min(1, before / Math.max(1, lengthOf(walk)));
    // Between two sentences, a step acting or being recorded: no words, the bar where it stands.
    if (step === null) return { lit: "", coming: "", beats: [], fraction };
    const now = this.audio.currentTime * 1000;
    const lit = step.words.filter((word) => word.startMs <= now).map((word) => word.text).join(" ");
    const rest = step.words.filter((word) => word.startMs > now).map((word) => word.text).join(" ");
    return {
      lit,
      coming: lit !== "" && rest !== "" ? ` ${rest}` : rest,
      beats: this.#player.due(this.#speech(walk), lit),
      fraction: Math.min(1, (before + now) / Math.max(1, lengthOf(walk))),
    };
  }

  /** Stop where it is: how far the visitor got, or null when nothing played. */
  stop(): Walked | null {
    const walk = this.#walk;
    if (walk === null) return null;
    const walked = { walk: walk.name, step: this.#step + 1, of: walk.steps.length, done: false };
    this.#reset();
    return walked;
  }

  /** From the step it stands on: acts done and sentences left out in turn, until a sentence plays or the walk ends. */
  async #go(): Promise<void> {
    const walk = this.#walk;
    const run = ++this.#run;
    while (walk !== null && run === this.#run) {
      const step: WalkStep | undefined = walk.steps[this.#step];
      if (step === undefined) return this.#finish(true);
      if (!taken(step, this.#values)) {
        this.#step += 1;
        continue;
      }
      this.#current = null;
      this.#player.drop();
      if (isAct(step)) {
        const read = await this.#hooks.act(step, this.#values, this.#step).catch(() => ({}));
        if (run !== this.#run) return;
        Object.assign(this.#values, read);
        this.#step += 1;
        continue;
      }
      const recorded = "live" in step ? await this.#hooks.voice(walk, this.#step, this.#values).catch(() => null) : step;
      if (run !== this.#run) return;
      if (recorded === null) {
        this.#step += 1;
        continue;
      }
      return this.#play({ ...recorded, beats: beatsFilled(recorded.beats, this.#values) });
    }
  }

  #play(step: RecordedStep): void {
    const walk = this.#walk;
    if (walk === null) return;
    if (this.#paused) {
      this.#held = step;
      return;
    }
    this.#current = step;
    const asStep: Step = { type: "macro.step", macro: walk.name, step: this.#step, say: step.say, beats: step.beats };
    this.#player.arm(asStep, null);
    this.#shows(step, this.#step);
    this.audio.src = step.audio;
    this.audio.play().catch(() => this.#finish(false));
  }

  #next(): void {
    if (this.#walk === null || this.#current === null) return;
    this.#step += 1;
    void this.#go();
  }

  #finish(done: boolean): void {
    const walk = this.#walk;
    if (walk === null) return;
    const walked = { walk: walk.name, step: done ? walk.steps.length : this.#step + 1, of: walk.steps.length, done };
    this.#reset();
    this.#ended(walked);
  }

  #reset(): void {
    this.#walk = null;
    this.#run += 1;
    this.#current = null;
    this.#held = null;
    this.#values = {};
    this.#paused = false;
    this.#player.drop();
    this.#shows(null, -1);
    this.audio.pause();
  }

  // The player binds a step to a "speech": a sentence of the walk is its own.
  #speech(walk: RecordedWalk): string {
    return `walk:${walk.name}:${this.#step}`;
  }
}
