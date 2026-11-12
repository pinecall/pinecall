/** `@agent({ … })`: what an agent is, declared once above its class. */

import type { EventDeclarations } from "./accepts.js";
import { judges, personas, type OwnJudge, type OwnPersona } from "./harness.js";
import type { HoldDeclaration } from "./melody.js";
import type { Ending, Opening } from "./opening.js";
import type { Task } from "./tasks.js";
import { DeclarationRefused } from "./tools.js";
import type { Visibility } from "./visibility.js";
import type { AgentConfig } from "../wire/agent-config.js";
import type { Camel } from "../wire/codec.js";

type Declared = Camel<AgentConfig>;

/** A stage's options beside its model: a class of the vendor's plugin, and its keyword arguments as the plugin names them. */
type StageOptions = Record<string, unknown>;

/** What an agent is. Each field declared wins over the agent's settings, and the console shows it set by the class. */
export interface AgentDeclaration {
  /** The class description, as an alternative to a JSDoc comment above the class. */
  doc?: string;
  /** The name the agent registers as; left out, its folder's name. A class served under another is refused. */
  slug?: string;
  /** The ears, `"vendor/model"`, or `{ model: "soniox/stt-rt-v3", endOfTurn: "smart-turn" }` with their options. */
  stt?: Declared["stt"] | string | (StageOptions & { model: string });
  /** The model that answers, `"vendor/model"`, or `{ model: "openai/gpt-5.4-mini", temperature: 0.2 }` with its options. */
  llm?: Declared["llm"] | string | (StageOptions & { model: string });
  /** The voice, `"vendor/voice id"`, or `{ voice: "cartesia/<id>", model: "sonic-2" }` with its options. */
  voice?: Declared["voice"] | string | (StageOptions & { voice: string });
  /** The model a voice call runs on alone, hearing and speaking itself; a written call runs on `llm`. */
  realtime?: Declared["realtime"] | string | (StageOptions & { model: string });
  /** The model the agent's calls are judged on. */
  judge?: Declared["judge"] | string | (StageOptions & { model: string });
  /** The language the agent speaks and expects, a BCP 47 tag: `"es"`, `"pt-BR"`. */
  language?: Declared["language"];
  timezone?: Declared["timezone"];
  /** How a call opens: the words, as a string, or `improvise` for the model's own. */
  greeting?: Opening;
  /** When the model may end the call: in your words, or `true` whenever it judges it done. */
  hangup?: Ending;
  turn?: Declared["turn"];
  /** How the voice says a word: `[{ word: "GSA", spoken: "G S A" }]`. */
  says?: Declared["says"];
  /** Words the ears must know. */
  hears?: Declared["hears"];
  /** Markdown read whole into every call: `{ path, text }`. */
  knowledge?: Declared["knowledge"];
  /** The knowledge base searched: `{ base: "clinica", k: 4 }`; `bases` for several, in place of it. */
  docs?: Declared["docs"];
  bases?: Declared["bases"];
  monitors?: Declared["monitors"];
  /** What memory keeps of a contact and never keeps: `{ remember: […], forget: […] }`. */
  memory?: Declared["memory"];
  /** Whether the calls keep their audio. */
  record?: Declared["record"];
  /** The longest a voice call runs, in minutes (1 to 60), or `"off"` for no limit. */
  maxDuration?: number | "off";
  /** How long a turn waits for the model's first word, in seconds. */
  llmTimeout?: number;
  /** How long a caller's silence ends a voice call, in whole seconds (5 to 3600). */
  silenceTimeout?: number;
  /** What the agent says to a caller gone quiet: `{ says: […], afterS, times }`. */
  idle?: Declared["idle"];
  /** On a call it placed, the words left on a machine, or `true` to leave nothing. */
  voicemail?: string | true;
  sttFallbacks?: Declared["sttFallbacks"];
  ttsFallbacks?: Declared["ttsFallbacks"];
  /** The judges its calls meet: a name is one of Pinecall's, an `ownJudge({ … })` its own. */
  judges?: (string | OwnJudge)[];
  /** The test callers its runs play: a name is one of Pinecall's, an `ownPersona({ … })` its own. */
  personas?: (string | OwnPersona)[];
  /** The hold melody: a file beside the class and the wait before it (`{ file: "hold.mp3", afterS: 1.5 }`), or `"off"`. */
  hold?: HoldDeclaration | "off";
  /** The scenes of the caller's screen, each with what it shows: `{ agenda: "the open times you last read" }`. */
  scenes?: Record<string, string>;
  /** How the widget presents the agent: `{ title, tagline, greeting, accent, autostart, theme }`. */
  widget?: Declared["widget"];
  /** What this agent takes when a teammate passes it a call, in words the model reads. */
  takes?: string;
  /** What a tool may stop to ask the caller for: `[GetEmail, GetPhone]`. */
  tasks?: Task<unknown>[];
  /** The external events the class accepts, and from whom. */
  events?: EventDeclarations;
  /** Field visibility as a map, as an alternative to `@state`. */
  visibility?: Record<string, Visibility>;
}

type Field = keyof AgentDeclaration;

// Written out so a name nobody declared is told from one: a type's keys are gone once compiled.
const FIELDS: ReadonlySet<string> = new Set<Field>([
  "doc", "slug", "stt", "llm", "voice", "realtime", "judge", "language", "timezone", "greeting", "hangup", "turn", "says", "hears",
  "knowledge", "docs", "bases", "monitors", "memory", "record", "maxDuration", "llmTimeout", "silenceTimeout", "idle",
  "voicemail", "sttFallbacks", "ttsFallbacks", "judges", "personas", "hold", "scenes", "widget", "takes", "tasks", "events",
  "visibility",
]);

// What each `@agent` put on its class. Kept outside the class, so a field the class wrote itself is told from these.
const DECLARED = new WeakMap<Function, ReadonlySet<string>>();

/**
 * Say what the agent is: `@agent({ stt: "deepgram/flux-general-en", llm: "google/gemini-3.5-flash-lite", voice: "cartesia/<id>" })`.
 * A subclass keeps what its parent declared and declares over it, field by field.
 */
export function agent(declaration: AgentDeclaration) {
  return function decorate(ctor: Function): void {
    if (DECLARED.has(ctor)) throw new DeclarationRefused(`${ctor.name} has two @agent({ … }): one says what it is`);
    const put = new Set<string>();
    for (const [field, value] of Object.entries(declaration)) {
      if (!FIELDS.has(field)) throw new DeclarationRefused(`${ctor.name}: @agent({ ${field} }) is nothing an agent declares`);
      if (value === undefined) continue;
      Object.defineProperty(ctor, field, { value: asRead(field, value), writable: true, configurable: true, enumerable: true });
      put.add(field);
    }
    DECLARED.set(ctor, put);
  };
}

/** One field as the class declared it, or as the class it extends did. The judges and the personas are `harnessOf`'s to read. */
export function declaredOf<F extends Exclude<Field, "judges" | "personas">>(ctor: Function, field: F): AgentDeclaration[F] {
  return (ctor as unknown as AgentDeclaration)[field];
}

/** Throw on a field the class declares as a `static`: there is one way to say what an agent is. */
export function refuseStatics(ctor: Function): void {
  for (let step: Function | null = ctor; typeof step === "function" && step !== Function.prototype; step = Object.getPrototypeOf(step) as Function | null) {
    const put = DECLARED.get(step);
    for (const field of FIELDS) {
      if (Object.hasOwn(step, field) && put?.has(field) !== true) {
        throw new DeclarationRefused(`${step.name} declares \`static ${field}\`: what an agent is goes in @agent({ ${field}: … }) above the class`);
      }
    }
  }
}

// A list names Pinecall's by their name and holds the class's own whole: read as the two lists the declaration sends.
function asRead(field: string, value: unknown): unknown {
  if (field !== "judges" && field !== "personas") return value;
  if (!Array.isArray(value)) throw new DeclarationRefused(`${field} is a list: a name for one of Pinecall's, an object for one of your own`);
  const on = value.filter((one): one is string => typeof one === "string");
  const own = value.filter((one) => typeof one !== "string");
  return field === "judges" ? judges({ on, own: own as OwnJudge[] }) : personas({ on, own: own as OwnPersona[] });
}
