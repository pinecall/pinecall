/** Settings form state and its conversion to and from the wire config. */

import { type TuningBody } from "@pinecall/core/wire/rest-org";

export type Modality = "stt" | "llm" | "tts";

/** What takes a model of its own: the three stages, and the model the agent's calls are judged on. */
export type Modeled = Modality | "judge";

/** A model knob as vendor + model picks; empty means the default. */
export interface Knob {
  vendor: string;
  model: string;
}

/** An attached base as form strings. */
export interface Attachment {
  base: string;
  /** Chunks per turn; empty for the runtime default. */
  k: string;
  /** Retrieval mode: platform before the turn, or model on demand. */
  mode: "retrieved" | "tool";
  /** Minimum fused score for this base; empty keeps everything. */
  min_score: string;
}

/** Set one field of the form. */
export type Change = <K extends keyof Typed>(field: K, value: Typed[K]) => void;

/** A stage's plugin: a class of the vendor's plugin other than its default, and its keyword arguments as JSON text. */
export interface Plugin {
  builds: string;
  options: string;
}

/** Form fields as strings; lists are one item per line. */
export interface Typed {
  stt: Knob;
  llm: Knob;
  tts: Knob;
  /** The model the agent's calls are judged on; empty is the org's choice, else Pinecall's. */
  judge: Knob;
  voice: string;
  /** The model's temperature; "" is the vendor's default. */
  temperature: string;
  /** Who ends the caller's turn; "" is the operator's choice for the ears. */
  end_of_turn: "" | "stt" | "livekit" | "smart-turn";
  plugins: Record<Modeled, Plugin>;
  /** A language tag; "" is not set, and the vendors run their own default. */
  language: string;
  /** Opening: literal words, or an instruction for the model. */
  opening: "say" | "reply";
  say: string;
  /** An instruction for the model's opening; "" is the prompt alone. */
  reply: string;
  /** Whether the caller may cut the opening short; by default they cannot. */
  interruptible: boolean;
  /** Whether the model may end the call: never, whenever it judges, or when `hangup` says. */
  hangs_up: "never" | "any" | "when";
  hangup: string;
  endpointing_ms: string;
  min_interruption_words: string;
  eot_threshold: string;
  eager_eot_threshold: string;
  /** Record audio; "" is unset and falls through. */
  record: "" | "on" | "off";
  /** Max voice call duration in seconds; "0" is no limit, "" falls through. */
  max_duration_s: string;
  remember: string;
  forget: string;
  knowledge: string;
  bases: Attachment[];
  note: string;
}

// Wire forms: `vendor`, `vendor/model`, or a bare model. A word that is not a known vendor is a model.
/** Parse a wire word into vendor and model picks. */
export function knobOf(value: string | null | undefined, vendors: ReadonlySet<string>): Knob {
  if (value === null || value === undefined || value === "") return { vendor: "", model: "" };
  const at = value.lastIndexOf("/");
  if (at >= 0) return { vendor: value.slice(0, at), model: value.slice(at + 1) };
  return vendors.has(value) ? { vendor: value, model: "" } : { vendor: "", model: value };
}

/** Build the wire word from two picks; empty when neither is set. */
export function wordOf(knob: Knob): string {
  if (knob.vendor === "") return knob.model;
  return knob.model === "" ? knob.vendor : `${knob.vendor}/${knob.model}`;
}

/** Form fields from a corner's config. */
export function typedOf(config: TuningBody, vendors: ReadonlySet<string>): Typed {
  const turn = config.turn ?? undefined;
  const memory = config.memory ?? undefined;
  const tts = knobOf(config.tts, vendors);
  // Legacy `tts_model` wins on the wire; it is folded into the pick and never written back.
  const ttsModel = config.tts_model ?? undefined;
  const greeting = config.greeting ?? undefined;
  const when = config.hangup?.when ?? undefined;
  return {
    stt: knobOf(config.stt, vendors),
    llm: knobOf(config.llm, vendors),
    judge: knobOf(config.judge, vendors),
    tts: ttsModel === undefined || ttsModel === "" ? tts : { ...tts, model: ttsModel },
    voice: config.voice ?? "",
    temperature: typeof config.temperature === "number" ? String(config.temperature) : "",
    end_of_turn: config.end_of_turn ?? "",
    plugins: {
      stt: pluginOf(config.stt_builds, config.stt_options),
      llm: pluginOf(config.llm_builds, config.llm_options),
      tts: pluginOf(config.tts_builds, config.tts_options),
      judge: pluginOf(config.judge_builds, config.judge_options),
    },
    language: config.language ?? "",
    // A reply, even empty, is the model's own opening.
    opening: typeof greeting?.reply === "string" ? "reply" : "say",
    say: greeting?.say ?? "",
    reply: greeting?.reply ?? "",
    interruptible: greeting?.allow_interruptions === true,
    hangs_up: config.hangup === undefined || config.hangup === null ? "never" : when === undefined || when === null || when === "" ? "any" : "when",
    hangup: when ?? "",
    endpointing_ms: typeof turn?.endpointing_ms === "number" ? String(turn.endpointing_ms) : "",
    min_interruption_words: typeof turn?.min_interruption_words === "number" ? String(turn.min_interruption_words) : "",
    eot_threshold: typeof turn?.eot_threshold === "number" ? String(turn.eot_threshold) : "",
    eager_eot_threshold: typeof turn?.eager_eot_threshold === "number" ? String(turn.eager_eot_threshold) : "",
    // Keep absent and false distinct: absent falls through to the corner below.
    record: typeof config.record === "boolean" ? (config.record ? "on" : "off") : "",
    max_duration_s: typeof config.max_duration_s === "number" ? String(config.max_duration_s) : "",
    remember: (memory?.remember ?? []).join("\n"),
    forget: (memory?.forget ?? []).join("\n"),
    knowledge: config.knowledge ?? "",
    bases: (config.bases ?? []).map((one) => ({
      base: one.base,
      k: typeof one.k === "number" ? String(one.k) : "",
      mode: one.mode === "tool" ? "tool" : "retrieved",
      min_score: typeof one.min_score === "number" ? String(one.min_score) : "",
    })),
    note: "",
  };
}

/** The wire fields each setting the class may declare covers, by the declaration's name. */
export const COVERED: Readonly<Record<string, readonly (keyof TuningBody)[]>> = {
  voice: ["voice", "tts", "tts_model", "tts_builds", "tts_options"],
  stt: ["stt", "stt_builds", "stt_options", "end_of_turn"],
  llm: ["llm", "temperature", "llm_builds", "llm_options"],
  judge: ["judge", "judge_builds", "judge_options"],
  language: ["language"],
  greeting: ["greeting"],
  hangup: ["hangup"],
  turn: ["turn"],
  memory: ["memory"],
  record: ["record"],
  knowledge: ["knowledge"],
  docs: ["bases"],
};

export const NOT_AN_OBJECT = (stage: Modeled): string => `The ${stage.toUpperCase()} plugin's options are not a JSON object: write them as {"name": value, …}, or leave the field empty.`;

// Empty fields are omitted (the door refuses ""), reverting to the runtime default. A words-only
// key keeps the corner's other fields and rewrites only its own three. A field the class fixes is
// sent as the corner had it: the class wins over it, and a change would be refused.
/** Full config to send from the form's fields; throws on plugin options that are not a JSON object. */
export function configOf(typed: Typed, wordsOnly: boolean, standing: TuningBody, fixed: ReadonlySet<string> = new Set()): TuningBody {
  const config = fromTheForm(typed, wordsOnly, standing);
  for (const name of fixed) {
    for (const field of COVERED[name] ?? []) {
      if (standing[field] === undefined || standing[field] === null) delete config[field];
      else (config as Record<string, unknown>)[field] = standing[field];
    }
  }
  return config;
}

function fromTheForm(typed: Typed, wordsOnly: boolean, standing: TuningBody): TuningBody {
  const config: TuningBody = wordsOnly ? { ...standing } : {};
  if (!wordsOnly) {
    for (const field of ["stt", "llm", "tts", "judge"] as const) {
      const word = wordOf(typed[field]);
      if (word !== "") config[field] = word;
      const plugin = typed.plugins[field];
      if (plugin.builds.trim() !== "") config[`${field}_builds`] = plugin.builds.trim();
      const options = optionsOf(field, plugin.options);
      if (options !== undefined) config[`${field}_options`] = options;
    }
    if (typed.temperature.trim() !== "") config.temperature = Number(typed.temperature);
    if (typed.end_of_turn !== "") config.end_of_turn = typed.end_of_turn;
    const voice = typed.voice.trim();
    if (voice !== "") config.voice = voice;
    const language = typed.language.trim();
    if (language !== "") config.language = language;
    const hangup = typed.hangup.trim();
    if (typed.hangs_up === "any" || (typed.hangs_up === "when" && hangup === "")) config.hangup = { when: "" };
    else if (typed.hangs_up === "when") config.hangup = { when: hangup };
    // Over the corner's own turn, so a knob this form does not show is kept, not dropped.
    const turn: NonNullable<TuningBody["turn"]> = { ...(standing.turn ?? {}) };
    numberInto(turn, "endpointing_ms", typed.endpointing_ms);
    numberInto(turn, "min_interruption_words", typed.min_interruption_words);
    numberInto(turn, "eot_threshold", typed.eot_threshold);
    numberInto(turn, "eager_eot_threshold", typed.eager_eot_threshold);
    if (Object.keys(turn).length > 0) config.turn = turn;
    if (typed.record !== "") config.record = typed.record === "on";
    if (typed.max_duration_s !== "") config.max_duration_s = Number(typed.max_duration_s);
    // Send only explicit choices, so runtime defaults can change without rewriting corners.
    const bases = typed.bases.filter((one) => one.base.trim() !== "").map(attachmentOf);
    // Always sent, even empty: a missing `bases` means unset and falls back to the team's.
    config.bases = bases;
  }
  const say = typed.say.trim();
  const interruptible = typed.interruptible ? { allow_interruptions: true } : {};
  // The model's own opening needs no instruction: empty, it opens on the prompt alone.
  if (typed.opening === "say" && say !== "") config.greeting = { say, ...interruptible };
  else if (typed.opening === "reply" && !wordsOnly) config.greeting = { reply: typed.reply.trim(), ...interruptible };
  else delete config.greeting;
  const remember = lines(typed.remember);
  const forget = lines(typed.forget);
  if (remember.length > 0 || forget.length > 0) config.memory = { remember, forget };
  else delete config.memory;
  if (typed.knowledge.trim() !== "") config.knowledge = typed.knowledge;
  else delete config.knowledge;
  return config;
}

type Knobs = NonNullable<TuningBody["turn"]>;

// An empty field takes the knob out; a number sets it.
function numberInto(turn: Knobs, knob: keyof Knobs, said: string): void {
  if (said.trim() === "") delete turn[knob];
  else turn[knob] = Number(said);
}

function pluginOf(builds: string | null | undefined, options: Record<string, unknown> | null | undefined): Plugin {
  return { builds: builds ?? "", options: options === null || options === undefined ? "" : JSON.stringify(options, null, 2) };
}

function optionsOf(stage: Modeled, text: string): Record<string, unknown> | undefined {
  if (text.trim() === "") return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(NOT_AN_OBJECT(stage));
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(NOT_AN_OBJECT(stage));
  return parsed as Record<string, unknown>;
}

function attachmentOf(one: Attachment): NonNullable<TuningBody["bases"]>[number] {
  const attached: NonNullable<TuningBody["bases"]>[number] = { base: one.base.trim() };
  if (one.k.trim() !== "") attached.k = Number(one.k);
  if (one.mode === "tool") attached.mode = "tool";
  if (one.min_score.trim() !== "") attached.min_score = Number(one.min_score);
  return attached;
}

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
