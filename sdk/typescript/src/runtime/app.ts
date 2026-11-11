/** A voice app: the numbers a project answers at, the agent that answers each, and what every agent of it shares. */

import type { Agent } from "../agent/agent.js";
import { DeclarationRefused } from "../agent/tools.js";
import type { AgentOptions } from "../client/agent.js";

type Ctor = new () => Agent;

/** A line as it is written: the agent that answers it, and the words the call opens with. */
export interface LineOptions {
  answers: Ctor;
  /** Said as written when the call comes in, before any model runs. */
  greeting?: string;
}

/** One number of the app and who answers it. */
export interface Line {
  number: string;
  answers: Ctor;
  greeting?: string;
}

/** What every agent of the app says to a caller who went quiet. */
export interface Silence {
  /** How long the caller says nothing: seconds, or `"8s"`. */
  after: number | string;
  say: string;
  /** How many times it is said before the agent stops asking. */
  times?: number;
}

// The brand a loader knows an app by: `instanceof` fails across two copies of the package.
const BRAND = Symbol.for("pinecall.voice-app");

const A_NAME = /^[a-z0-9][a-z0-9-]*$/;
const A_NUMBER = /^\+[1-9]\d{6,14}$/;
const SECONDS = /^(\d+)s$/;

const NOT_A_NAME = "a voice app's name is lowercase letters, digits and dashes, like its project's folder";
const NOT_A_NUMBER = "a line is a phone number with its country code, like +1 415 555 0134";
const NOT_AN_AGENT = "a line is answered by an agent class: app.line(number, FrontDesk)";
const NOT_A_SILENCE = "silence is { after, say }: after in seconds (8, or \"8s\"), say the words to a caller who went quiet";

/** A voice app. `line` and `silence` return the app, so they chain. */
export class VoiceApp {
  readonly [BRAND] = true;
  readonly name: string;
  readonly #lines: Line[] = [];
  #silence: AgentOptions["idle"] | undefined;

  constructor(name: string) {
    if (typeof name !== "string" || !A_NAME.test(name)) throw new DeclarationRefused(NOT_A_NAME);
    this.name = name;
  }

  /** Answer `number` with an agent: `app.line(number, FrontDesk)`, or with `{ answers, greeting }`. */
  line(number: string, answered: Ctor | LineOptions): this {
    const dialled = typeof number === "string" ? number.replace(/[\s().-]/g, "") : "";
    if (!A_NUMBER.test(dialled)) throw new DeclarationRefused(NOT_A_NUMBER);
    if (this.#lines.some((line) => line.number === dialled)) throw new DeclarationRefused(`${dialled} is a line of ${this.name} already`);
    const options: LineOptions = typeof answered === "function" ? { answers: answered } : answered;
    if (typeof options?.answers !== "function") throw new DeclarationRefused(NOT_AN_AGENT);
    const greeting = options.greeting;
    if (greeting !== undefined && (typeof greeting !== "string" || greeting.trim() === "")) {
      throw new DeclarationRefused(`the greeting of ${dialled} is the words the call opens with`);
    }
    // The gateway opens a call on its agent's declaration, which does not know the line yet.
    const other = this.#lines.find((line) => line.answers === options.answers && line.greeting !== greeting);
    if (other !== undefined) {
      throw new DeclarationRefused(`${options.answers.name} answers ${other.number} and ${dialled}: both lines open with the same greeting, or with none`);
    }
    this.#lines.push({ number: dialled, answers: options.answers, ...(greeting === undefined ? {} : { greeting }) });
    return this;
  }

  /** What every agent of the app says to a caller who went quiet, and after how long. */
  silence(silence: Silence): this {
    const after = secondsOf(silence?.after);
    if (after === null || typeof silence.say !== "string" || silence.say.trim() === "") throw new DeclarationRefused(NOT_A_SILENCE);
    if (silence.times !== undefined && (!Number.isInteger(silence.times) || silence.times < 1)) throw new DeclarationRefused(NOT_A_SILENCE);
    this.#silence = { says: [silence.say], afterS: after, ...(silence.times === undefined ? {} : { times: silence.times }) };
    return this;
  }

  /** The lines, in the order they were written. */
  get lines(): readonly Line[] {
    return this.#lines;
  }

  /** Every agent class the app names, once each. */
  agents(): Ctor[] {
    return [...new Set(this.#lines.map((line) => line.answers))];
  }

  /** The numbers `ctor` answers. */
  numbersOf(ctor: Ctor): string[] {
    return this.#lines.filter((line) => line.answers === ctor).map((line) => line.number);
  }

  /**
   * What the app adds to the declaration of one of its agents. A setting the class declares itself
   * and the app declares too is refused: nobody should have to guess which one a call runs on.
   */
  declares(ctor: Ctor): Partial<AgentOptions> {
    const own = ctor as unknown as Record<string, unknown>;
    const added: Partial<AgentOptions> = {};
    const greeting = this.#lines.find((line) => line.answers === ctor && line.greeting !== undefined)?.greeting;
    if (greeting !== undefined) {
      if (own["greeting"] !== undefined) throw new DeclarationRefused(twice(ctor, "greeting", "its line's greeting", this.name));
      added.greeting = { say: greeting };
    }
    if (this.#silence !== undefined && this.agents().includes(ctor)) {
      if (own["idle"] !== undefined) throw new DeclarationRefused(twice(ctor, "idle", "app.silence", this.name));
      added.idle = this.#silence;
    }
    return added;
  }
}

function twice(ctor: Ctor, field: string, appSays: string, app: string): string {
  return `${ctor.name} declares \`static ${field}\` and ${app} declares ${appSays}: keep one of the two`;
}

function secondsOf(given: unknown): number | null {
  if (typeof given === "number") return given > 0 ? given : null;
  const found = typeof given === "string" ? SECONDS.exec(given.trim()) : null;
  return found === null ? null : Number(found[1]);
}

/** A voice app named as its project: `const app = voiceApp("brightside")`. */
export function voiceApp(name: string): VoiceApp {
  return new VoiceApp(name);
}

/** Whether a module's export is a voice app, of this copy of the package or another. */
export function isVoiceApp(given: unknown): given is VoiceApp {
  return typeof given === "object" && given !== null && (given as Record<symbol, unknown>)[BRAND] === true;
}
