/** An agent as its app declares it to the gateway: voice, models, turns, views, docs, memory. */

import { z } from "zod";
import {
  DocsModeSchema,
  EventSourceSchema,
  PromptBlockSpecSchema,
  ToolSpecSchema,
  VisibilitySchema,
} from "./defs.js";
import { JudgeAnswerSchema, JudgeReadSchema, JudgeWhenSchema } from "./rest-judges.js";

/** Which voice speaks for the agent: the name it was asked for, or the id the provider knows it by. */
export const VoiceConfigSchema = z.strictObject({
  name: z.string().nullish(),
  provider: z.string().nullish(),
  model: z.string().nullish(),
  voice_id: z.string().nullish(),
  // A class of the vendor's livekit plugin other than its TTS, and its keyword arguments.
  builds: z.string().nullish(),
  options: z.record(z.string(), z.unknown()).nullish(),
});

export type VoiceConfig = z.infer<typeof VoiceConfigSchema>;

/** Who says the caller's turn is over: the ears themselves, livekit's detector, or Smart Turn v3. */
export const EndOfTurnSchema = z.enum(["stt", "livekit", "smart-turn"]);

export type EndOfTurn = z.infer<typeof EndOfTurnSchema>;

/** Which model does a job (the LLM, or the STT), and the one or two knobs worth turning. */
export const ModelConfigSchema = z.strictObject({
  provider: z.string(),
  model: z.string(),
  temperature: z.number().nullish(),
  // A class of the vendor's livekit plugin other than its LLM or STT (`responses.LLM`), and its
  // keyword arguments as the plugin names them (`{ use_websocket: true }`).
  builds: z.string().nullish(),
  options: z.record(z.string(), z.unknown()).nullish(),
  // The ears' alone: who says the caller's turn is over.
  end_of_turn: EndOfTurnSchema.nullish(),
});

export type ModelConfig = z.infer<typeof ModelConfigSchema>;

/** How the session decides that the caller has finished, and when the caller may interrupt. */
export const TurnConfigSchema = z.strictObject({
  min_interruption_words: z.int().nullish(),
  endpointing_ms: z.int().nullish(),
  eot_threshold: z.number().nullish(),
  eager_eot_threshold: z.number().nullish(),
});

/** How the voice says one word it would otherwise get wrong: a proper name, a brand, a street. */
export const PronunciationSchema = z.strictObject({
  word: z.string(),
  spoken: z.string(),
});

/**
 * What the app declares about one field of its state: who may see it. A field never declared is
 * tenant.
 */
export const StateFieldSpecSchema = z.strictObject({
  name: z.string(),
  visibility: VisibilitySchema,
});

/**
 * The panel the agent draws beside a conversation: it is declared here so a console knows the
 * agent has one before it asks for it, and draws its own about the contact when it has not. What
 * the panel CONTAINS never comes this way — it is asked for a conversation at a time, through the
 * view.render dev verb.
 */
export const ViewSpecSchema = z.strictObject({
  name: z.string(),
});

/**
 * One outside event the agent accepts, and from whom. An event nobody declared is refused before
 * it touches the log.
 */
export const EventSpecSchema = z.strictObject({
  name: z.string(),
  from: z.array(EventSourceSchema),
});

/** One file of a base, as a push sends it: its path as the tenant keeps it, and its text. */
export const KnowledgeFileSchema = z.strictObject({
  path: z.string(),
  text: z.string(),
});

export type KnowledgeFile = z.infer<typeof KnowledgeFileSchema>;

/**
 * The knowledge base the agent answers from, and how its chunks reach the model. It is named by
 * the base it was pushed under, with PUT /v1/knowledge/{base}.
 */
export const DocsConfigSchema = z.strictObject({
  base: z.string(),
  mode: DocsModeSchema.nullish(),
  k: z.int().nullish(),
  min_score: z.number().nullish(),
});

export type DocsConfig = z.infer<typeof DocsConfigSchema>;

/**
 * How the agent opens a call, before the caller has said anything. Exactly one of the two, because
 * there are only two ways to open one: `say` are the words themselves and `reply` is what the
 * model is told before it finds its own. They are agent.say and agent.reply declared instead of
 * called, so a class that opens every call the same way needs no onCall hook to do it, and an
 * operator can turn the opening at the pipeline door without a deploy. Absent: nobody speaks until
 * the caller does.
 */
export const GreetingConfigSchema = z.strictObject({
  say: z.string().nullish(),
  reply: z.string().nullish(),
  allow_interruptions: z.boolean().nullish(),
});

/**
 * Whether the model may end the call itself. Declaring this is what puts livekit's own end_call
 * tool in front of the model; a class that says nothing here cannot hang up, and the call ends
 * when the caller does or when a supervisor says so. The tool is hidden while the agent is
 * greeting, because a model that can hang up on its first turn eventually does.
 */
export const HangupConfigSchema = z.strictObject({
  when: z.string().nullish(),
});

/**
 * What memory keeps about a contact across calls, and what it must never keep. Both lists are in
 * the tenant's own words.
 */
export const MemoryConfigSchema = z.strictObject({
  remember: z.array(z.string()).nullish(),
  forget: z.array(z.string()).nullish(),
});

/**
 * What an app declares about its agent: the prompt's layout, the tools, whether it searches its
 * bases itself, and who may see and send what. Every field is optional so a configure can change
 * one thing. The environment — language, voice, models, greeting, hangup, turn, says, hears,
 * knowledge, docs, memory, record — is the agent's settings' unless the class declares it: what
 * the class declares wins over the settings.
 */
/** One judge of the agent's own, as its class declares it: `judges/<name>.md` read. */
export const JudgeDeclarationSchema = z.strictObject({
  name: z.string(),
  question: z.string(),
  answer: JudgeAnswerSchema.optional(),
  choices: z.array(z.string()).optional(),
  when: JudgeWhenSchema.optional(),
  trigger: z.string().optional(),
  reads: z.array(JudgeReadSchema).optional(),
});

export type JudgeDeclaration = z.infer<typeof JudgeDeclarationSchema>;

/** The judges the class owns: which of Pinecall's its calls meet (`on`), and its own. */
export const JudgesDeclaredSchema = z.strictObject({
  on: z.array(z.string()).optional(),
  own: z.array(JudgeDeclarationSchema).optional(),
});

export type JudgesDeclared = z.infer<typeof JudgesDeclaredSchema>;

/** What plays behind a simulated caller once `interferer_db` names a level. */
export const AmbienceSchema = z.enum(["television", "cafe", "office", "street"]);

/** How a simulated caller acts on a spoken line, beside what it says; each share is 0 to 1. */
export const CallerBehaviorSchema = z.strictObject({
  interrupts: z.number().optional(),
  pause_s: z.number().optional(),
  interferer_db: z.number().nullish(),
  packet_loss: z.number().optional(),
  backchannels: z.number().optional(),
  speed: z.number().optional(),
  ambience: AmbienceSchema.optional(),
});

export type CallerBehavior = z.infer<typeof CallerBehaviorSchema>;

/** One caller of the agent's own, as its class declares it: `test/personas/<name>.json` read. */
export const PersonaDeclarationSchema = z.strictObject({
  name: z.string(),
  goal: z.string(),
  style: z.string(),
  about: z.string().optional(),
  facts: z.record(z.string(), z.string()).optional(),
  state: z.record(z.string(), z.unknown()).optional(),
  expects: z.array(z.string()).optional(),
  tags: z.array(z.string()).optional(),
  behavior: CallerBehaviorSchema.optional(),
  llm: z.string().nullish(),
  tts: z.string().nullish(),
  voice: z.string().nullish(),
});

export type PersonaDeclaration = z.infer<typeof PersonaDeclarationSchema>;

/** The personas the class owns: which of Pinecall's its runs play (`on`), and its own. */
export const PersonasDeclaredSchema = z.strictObject({
  on: z.array(z.string()).optional(),
  own: z.array(PersonaDeclarationSchema).optional(),
});

export type PersonasDeclared = z.infer<typeof PersonasDeclaredSchema>;

export const AgentConfigSchema = z.strictObject({
  prompt: z.array(PromptBlockSpecSchema).nullish(),
  language: z.string().nullish(),
  greeting: GreetingConfigSchema.nullish(),
  voice: VoiceConfigSchema.nullish(),
  llm: ModelConfigSchema.nullish(),
  /** The model a voice call runs on alone, hearing and speaking itself; a written call runs on `llm`. */
  realtime: ModelConfigSchema.nullish(),
  stt: ModelConfigSchema.nullish(),
  /** The model the agent's calls are judged on, over the org's and the platform's. */
  judge: ModelConfigSchema.nullish(),
  turn: TurnConfigSchema.nullish(),
  says: z.array(PronunciationSchema).nullish(),
  hears: z.array(z.string()).nullish(),
  knowledge: KnowledgeFileSchema.nullish(),
  docs: DocsConfigSchema.nullish(),
  memory: MemoryConfigSchema.nullish(),
  hangup: HangupConfigSchema.nullish(),
  record: z.boolean().nullish(),
  /** The longest a voice call runs, in seconds (0 for no limit), and how long a turn waits for the model's first word. */
  max_duration_s: z.int().nullish(),
  llm_timeout_s: z.number().nullish(),
  tools: z.array(ToolSpecSchema).nullish(),
  uses_knowledge: z.boolean().nullish(),
  state_fields: z.array(StateFieldSpecSchema).nullish(),
  view: ViewSpecSchema.nullish(),
  events: z.array(EventSpecSchema).nullish(),
  /** Declared, the class owns the agent's judges and its personas: no door writes either. */
  judges: JudgesDeclaredSchema.nullish(),
  personas: PersonasDeclaredSchema.nullish(),
});

export type AgentConfig = z.infer<typeof AgentConfigSchema>;
