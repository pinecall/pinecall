/** A voice app: the numbers a project answers at, the agent that answers each, and what every agent of it shares. */

import { Agent } from "../agent/agent.js";
import { harnessOf, judges } from "../agent/harness.js";
import { DeclarationRefused } from "../agent/tools.js";
import type { AgentOptions } from "../client/agent.js";

import { isFlow, type Flow } from "./flows.js";
import { takenBy, type Answering } from "./handoff.js";

type Ctor = new () => Agent;

/** A line as it is written: the agent that answers it, and the words the call opens with. */
export interface LineOptions {
  /** The agent that answers, or a function that picks one of the team for each call. */
  answers: Ctor | Answering;
  /** With a function: the agent the number is pointed at, which answers when the function picks nobody, fails or is late. */
  fallback?: Ctor;
  /** Said as written when the call comes in, before any model runs. */
  greeting?: string;
  /** The agents the call may pass to: each says what it takes, `@agent({ takes: "…" })`. */
  team?: Ctor[];
}

/** One number of the app and who answers it. */
export interface Line {
  number: string;
  answers: Ctor;
  greeting?: string;
  team: Ctor[];
  /** The line's `answers` when it is a function. */
  chooses?: Answering;
}

/** The app's page: the built folder the platform serves at the app's own name, and the agent a visitor of it reaches. */
export interface Page {
  /** The folder of the built page, from the project's root: `ui/dist`. Its `index.html` is the page. */
  dir: string;
  answers: Ctor;
}

/** What every agent of the app says to a caller who went quiet. */
export interface Silence {
  /** How long the caller says nothing: seconds, or `"8s"`. */
  after: number | string;
  say: string;
  /** How many times it is said before the agent stops asking. */
  times?: number;
}

/** The call an entry belongs to, as a handler of the app is told it; `id` is null for an entry of no call. */
export interface Heard {
  id: string | null;
  /** The slug the gateway knows the call's agent by. */
  agent: string;
}

/** A handler of `app.on`: the call, and what the entry carries. */
export type Hearing = (call: Heard, data: Record<string, unknown>) => unknown;

/** An entry of a call's log, as much of it as the app reads. */
interface Logged {
  type: string;
  call: string | null;
  agent: string;
  data: Record<string, unknown>;
}

// The type of the entry a line an agent logs is kept as: its own name is inside it.
const A_LOGGED_LINE = "custom";

/** What a voice app is made with. */
export interface AppOptions {
  /** The IANA zone the app's agents read their day and their clock in: `"America/Los_Angeles"`. */
  timezone?: string;
}

// The brand a loader knows an app by: `instanceof` fails across two copies of the package.
const BRAND = Symbol.for("pinecall.voice-app");

const A_NAME = /^[a-z0-9][a-z0-9-]*$/;
const A_NUMBER = /^\+[1-9]\d{6,14}$/;
const SECONDS = /^(\d+)s$/;

const NOT_A_ZONE = "a voice app's timezone is an IANA zone, like America/Los_Angeles or Europe/Madrid";
const NOT_A_NAME = "a voice app's name is lowercase letters, digits and dashes, like its project's folder";
const NOT_A_NUMBER = "a line is a phone number with its country code, like +1 415 555 0134";
const NOT_AN_AGENT = "a line is answered by an agent class: app.line(number, FrontDesk)";
const NOT_HEARD = "app.on takes the name of an entry and the function that hears it, or the flow it starts";
const NOT_A_PAGE = "a page is the folder its build writes, inside the project: app.page(\"ui/dist\")";
const NO_AGENT_FOR_A_PAGE = "a page's visitors reach an agent: write a line before the page, or name one with app.page(dir, { answers: FrontDesk })";
const NOT_A_SILENCE = "silence is { after, say }: after in seconds (8, or \"8s\"), say the words to a caller who went quiet";

/** A voice app. `line` and `silence` return the app, so they chain. */
export class VoiceApp {
  readonly [BRAND] = true;
  readonly name: string;
  readonly timezone: string | undefined;
  readonly #lines: Line[] = [];
  #silence: AgentOptions["idle"] | undefined;
  #page: Page | undefined;
  readonly #rules: string[] = [];
  readonly #hearing = new Map<string, Hearing[]>();
  readonly #starting = new Map<string, Flow[]>();

  constructor(name: string, options: AppOptions = {}) {
    if (typeof name !== "string" || !A_NAME.test(name)) throw new DeclarationRefused(NOT_A_NAME);
    if (options.timezone !== undefined && !isAZone(options.timezone)) throw new DeclarationRefused(NOT_A_ZONE);
    this.name = name;
    this.timezone = options.timezone;
  }

  /** Answer `number` with an agent: `app.line(number, FrontDesk)`, or with `{ answers, greeting }`. */
  line(number: string, answered: Ctor | LineOptions): this {
    const dialled = typeof number === "string" ? number.replace(/[\s().-]/g, "") : "";
    if (!A_NUMBER.test(dialled)) throw new DeclarationRefused(NOT_A_NUMBER);
    if (this.#lines.some((line) => line.number === dialled)) throw new DeclarationRefused(`${dialled} is a line of ${this.name} already`);
    const options: LineOptions = typeof answered === "function" ? { answers: answered } : answered;
    if (typeof options?.answers !== "function") throw new DeclarationRefused(NOT_AN_AGENT);
    const chooses = isAnAgent(options.answers) ? undefined : (options.answers as Answering);
    const bound = chooses === undefined ? (options.answers as Ctor) : options.fallback;
    if (bound === undefined || !isAnAgent(bound)) throw new DeclarationRefused(`${dialled}: a line whose answers is a function names its fallback, the agent the number is pointed at`);
    const greeting = options.greeting;
    if (greeting !== undefined && (typeof greeting !== "string" || greeting.trim() === "")) {
      throw new DeclarationRefused(`the greeting of ${dialled} is the words the call opens with`);
    }
    // The gateway opens a call on its agent's declaration, which does not know the line yet.
    const other = this.#lines.find((line) => line.answers === bound && line.greeting !== greeting);
    if (other !== undefined) {
      throw new DeclarationRefused(`${bound.name} answers ${other.number} and ${dialled}: both lines open with the same greeting, or with none`);
    }
    const team = options.team ?? [];
    if (!Array.isArray(team) || team.some((mate) => typeof mate !== "function")) throw new DeclarationRefused(`the team of ${dialled} is a list of agent classes`);
    for (const mate of team) {
      if (takenBy(mate) === undefined) throw new DeclarationRefused(`${mate.name} is of the team of ${dialled} and says nothing of what it takes: @agent({ takes: "…" })`);
    }
    if (chooses !== undefined && team.length === 0) throw new DeclarationRefused(`${dialled}: a function answers with one of the line's team, and this line names none`);
    this.#lines.push({ number: dialled, answers: bound, team, ...(greeting === undefined ? {} : { greeting }), ...(chooses === undefined ? {} : { chooses }) });
    return this;
  }

  /**
   * A rule every agent of the app keeps: it is read into each one's prompt, and a judge asks of every
   * call whether it was kept. `app.rule("Never quote a price that is not in the price list.")`
   */
  rule(rule: string): this {
    if (typeof rule !== "string" || rule.trim() === "") throw new DeclarationRefused("a rule is a sentence every agent of the app keeps");
    this.#rules.push(rule.trim());
    return this;
  }

  /**
   * Run `handler` on every entry of that name on a call of the app's agents: an entry of the call's
   * log by its type (`"call.ended"`, `"call.score"`), or a line an agent logs by its name
   * (`this.log("visit.booked", visit)` reaches `app.on("visit.booked", …)`), or an event sent to the
   * app. With a flow in place of the function, the entry starts a run of it, once, with what it carries.
   */
  on(name: string, handler: Hearing | Flow): this {
    if (typeof name !== "string" || name.trim() === "") throw new DeclarationRefused(NOT_HEARD);
    if (isFlow(handler)) {
      const other = this.flows().find((flow) => flow.name === handler.name && flow !== handler);
      if (other !== undefined) throw new DeclarationRefused(`two flows of ${this.name} are named ${handler.name}: a run is kept by its flow's name`);
      this.#starting.set(name, [...(this.#starting.get(name) ?? []), handler]);
      return this;
    }
    if (typeof handler !== "function") throw new DeclarationRefused(NOT_HEARD);
    this.#hearing.set(name, [...(this.#hearing.get(name) ?? []), handler]);
    return this;
  }

  /** Every flow the app starts, once each. */
  flows(): Flow[] {
    return [...new Set([...this.#starting.values()].flat())];
  }

  /** The flows an entry of that name starts. */
  startedBy(name: string): readonly Flow[] {
    return this.#starting.get(name) ?? [];
  }

  /** The name an entry is heard by and what it carries: a line an agent logs is heard by its own name. */
  named(entry: Logged): { name: string; data: Record<string, unknown> } {
    if (entry.type !== A_LOGGED_LINE) return { name: entry.type, data: entry.data };
    return { name: String(entry.data["name"] ?? ""), data: (entry.data["data"] as Record<string, unknown> | undefined) ?? {} };
  }

  /** Hand one entry to whoever asked for its name, in the order they asked; a handler that throws is told to `failed` and the rest run. */
  async heard(entry: Logged, failed: (name: string, error: Error) => void = () => {}): Promise<void> {
    const { name, data } = this.named(entry);
    for (const handler of this.#hearing.get(name) ?? []) {
      try {
        await handler({ id: entry.call, agent: entry.agent }, data);
      } catch (thrown) {
        failed(name, thrown instanceof Error ? thrown : new Error(String(thrown)));
      }
    }
  }

  /** The app's rules, in the order they were written. */
  get rules(): readonly string[] {
    return this.#rules;
  }

  /**
   * The app's page: `app.page("ui/dist")`. `pinecall deploy` sends the folder with the release and the
   * platform serves it at the app's own name; a visitor of it reaches the agent of the app's first line,
   * or the one `answers` names.
   */
  page(dir: string, options: { answers?: Ctor } = {}): this {
    const folder = typeof dir === "string" ? dir.replace(/^\.\//, "").replace(/\/+$/, "") : "";
    if (folder === "" || folder.startsWith("/") || folder.split("/").includes("..")) throw new DeclarationRefused(NOT_A_PAGE);
    if (this.#page !== undefined) throw new DeclarationRefused(`${this.name} has its page already, ${this.#page.dir}: an app has one`);
    const answers = options.answers ?? this.#lines[0]?.answers;
    if (answers === undefined || !isAnAgent(answers)) throw new DeclarationRefused(NO_AGENT_FOR_A_PAGE);
    this.#page = { dir: folder, answers };
    return this;
  }

  /** The app's page, when it has one. */
  get paged(): Page | undefined {
    return this.#page;
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
    return [...new Set([...this.#lines.flatMap((line) => [line.answers, ...line.team]), ...(this.#page === undefined ? [] : [this.#page.answers])])];
  }

  /** The function that picks who serves each call of the line `ctor` is bound to; undefined when the line names its agent. */
  choosing(ctor: Ctor): Answering | undefined {
    return this.#lines.find((line) => line.answers === ctor && line.chooses !== undefined)?.chooses;
  }

  /** The agents a call of `ctor` may pass between, itself first; empty for an agent of no team. */
  teamOf(ctor: Ctor): Ctor[] {
    const lines = this.#lines.filter((line) => line.team.length > 0 && (line.answers === ctor || line.team.includes(ctor)));
    return [...new Set(lines.flatMap((line) => [line.answers, ...line.team]))];
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
    const ofTheApp = this.agents().includes(ctor);
    if (this.timezone !== undefined && ofTheApp) {
      if (own["timezone"] !== undefined) throw new DeclarationRefused(twice(ctor, "timezone", "its own timezone", this.name));
      added.timezone = this.timezone;
    }
    if (this.#rules.length > 0 && ofTheApp) {
      // The class's own judges stay, and each rule adds one: a declared list is the agent's whole list.
      const own = harnessOf(ctor).judges ?? { on: [], own: [] };
      const asked = this.#rules.map((rule, at) => ({ name: `app-rule-${at + 1}`, question: `Did the agent keep this rule through the whole call: "${rule}"?` }));
      added.judges = judges({ on: own.on ?? [], own: [...(own.own ?? []), ...asked] });
    }
    if (this.#silence !== undefined && ofTheApp) {
      if (own["idle"] !== undefined) throw new DeclarationRefused(twice(ctor, "idle", "app.silence", this.name));
      added.idle = this.#silence;
    }
    return added;
  }
}

// A class and a function are both functions: an agent is one whose instances are Agents.
function isAnAgent(given: unknown): given is Ctor {
  return typeof given === "function" && (given as { prototype?: unknown }).prototype instanceof Agent;
}

function twice(ctor: Ctor, field: string, appSays: string, app: string): string {
  return `${ctor.name} declares \`static ${field}\` and ${app} declares ${appSays}: keep one of the two`;
}

function secondsOf(given: unknown): number | null {
  if (typeof given === "number") return given > 0 ? given : null;
  const found = typeof given === "string" ? SECONDS.exec(given.trim()) : null;
  return found === null ? null : Number(found[1]);
}

// The runtime checks it again; here a typo is refused where it was typed.
function isAZone(given: unknown): boolean {
  if (typeof given !== "string" || given.trim() === "") return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: given });
    return true;
  } catch {
    return false;
  }
}

/** A voice app named as its project: `const app = voiceApp("brightside", { timezone: "America/Los_Angeles" })`. */
export function voiceApp(name: string, options: AppOptions = {}): VoiceApp {
  return new VoiceApp(name, options);
}

/** Whether a module's export is a voice app, of this copy of the package or another. */
export function isVoiceApp(given: unknown): given is VoiceApp {
  return typeof given === "object" && given !== null && (given as Record<symbol, unknown>)[BRAND] === true;
}
