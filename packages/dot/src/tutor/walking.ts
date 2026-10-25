/** A recorded walk played on the page with no call: its sentences in the agent's voice, their words lit as said, the beats on their words. */
//
// One audio element plays every sentence in turn: Safari lets an element the visitor's click
// started go on to its next source, where a new element would need another click. Each frame
// reads where the audio is, so the words and the pointer follow the sound, whatever the network.

import { walksOf, type Beat, type RecordedStep, type RecordedWalk, type Step } from "../wire/index.js";
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

/** The walks an agent published, read with no key; none where the page cannot read them. */
export async function publishedWalks(url: string): Promise<RecordedWalk[]> {
  if (url === "") return [];
  try {
    const answer = await fetch(url);
    return answer.ok ? walksOf(await answer.json()) : [];
  } catch {
    return [];
  }
}

/** A walk's length, in ms. */
export function lengthOf(walk: RecordedWalk): number {
  return walk.steps.reduce((total, step) => total + step.durationMs, 0);
}

export class Walking {
  readonly audio: HTMLAudioElement;
  readonly #ended: (walked: Walked) => void;
  readonly #shows: (step: RecordedStep | null) => void;
  readonly #player = new Player();
  #walk: RecordedWalk | null = null;
  #step = 0;
  #paused = false;

  /**
   * Play through `audio`; `ended` hears a walk that played to its end, or failed to play; `shows`
   * hears each sentence as it starts, for what it shows beside the page, and null as the walk stops.
   */
  constructor(audio: HTMLAudioElement, ended: (walked: Walked) => void, shows: (step: RecordedStep | null) => void = () => undefined) {
    this.audio = audio;
    this.#ended = ended;
    this.#shows = shows;
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
    this.audio.play().catch(() => this.#finish(false));
  }

  /** Play a walk from its first sentence. Call it from the visitor's click: a browser starts audio only inside one. */
  start(walk: RecordedWalk): void {
    this.#walk = walk;
    this.#step = 0;
    this.#play();
  }

  /** Where the walk is now; null while none plays. */
  frame(): WalkFrame | null {
    const walk = this.#walk;
    const step = walk?.steps[this.#step];
    if (walk === null || step === undefined) return null;
    const now = this.audio.currentTime * 1000;
    const lit = step.words.filter((word) => word.startMs <= now).map((word) => word.text).join(" ");
    const rest = step.words.filter((word) => word.startMs > now).map((word) => word.text).join(" ");
    const before = walk.steps.slice(0, this.#step).reduce((total, one) => total + one.durationMs, 0);
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

  #play(): void {
    const walk = this.#walk;
    const step = walk?.steps[this.#step];
    if (walk === null || step === undefined) return;
    const asStep: Step = { type: "macro.step", macro: walk.name, step: this.#step, say: step.say, beats: step.beats };
    this.#player.arm(asStep, null);
    this.#shows(step);
    this.audio.src = step.audio;
    this.audio.play().catch(() => this.#finish(false));
  }

  #next(): void {
    const walk = this.#walk;
    if (walk === null) return;
    if (this.#step + 1 < walk.steps.length) {
      this.#step += 1;
      this.#play();
      return;
    }
    this.#finish(true);
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
    this.#paused = false;
    this.#player.drop();
    this.#shows(null);
    this.audio.pause();
  }

  // The player binds a step to a "speech": a sentence of the walk is its own.
  #speech(walk: RecordedWalk): string {
    return `walk:${walk.name}:${this.#step}`;
  }
}
