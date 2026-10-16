/** The shapes the rest of the wire is made of: channels, parts of a turn, costs, scores. */

import { z } from "zod";

/**
 * The door the public came through: a phone call over SIP, the browser widget over WebRTC, or
 * WhatsApp text.
 */
export const ChannelSchema = z.enum(["phone", "web", "whatsapp"]);

/** Whether a call is spoken or written: the widget's voice call and its chat share the `web` channel. */
export const MediumSchema = z.enum(["voice", "text"]);

/** Inbound: the public reached the agent. Outbound: the agent reached out (a dial). */
export const DirectionSchema = z.enum(["inbound", "outbound"]);

/**
 * Which of the two worlds a key opens, and so which world an agent is held in and a call ran in. A
 * key is issued into one; an agent registered on it and every call it takes carry that one; a door
 * claimed in one is refused to a key of the other. `sandbox` is where things are written and
 * `production` is what the public reaches — and whether a sandbox agent is one PERSON's copy or
 * the team's shared one is not this field: it is whether the key that registered it names a
 * person. Every key issued before the field existed is production.
 */
export const EnvSchema = z.enum(["production", "sandbox"]);

/**
 * What a console may ask of the process standing in the agent's directory, relayed by the gateway:
 * a written call to the class mounted there (chat), a simulated caller put on the class it holds,
 * its goldens and a suite of them, its knowledge folder pushed or its golden asked, its memory
 * goldens, the panel it draws beside a conversation (view), a call promoted to a candidate file,
 * the drift of the last two windows, and the reproductions a broken run left on that disk.
 * Everything else a console needs is a door of the gateway.
 */
export const DevVerbSchema = z.enum(["chat.roster", "chat.start", "chat.say", "chat.end", "view.render", "simulate.start", "goldens.roster", "goldens.run", "knowledge.roster", "knowledge.push", "knowledge.eval", "memory.roster", "memory.eval", "memory.extraction", "promote.roster", "promote.write", "drift.read", "reproductions.roster", "reproductions.read"]);

export type DevVerb = z.infer<typeof DevVerbSchema>;

/**
 * Why the call is over. Who hung up, what failed before anybody could, drained: the platform took
 * the worker down (a deploy, a stop) with the call still on it, or app_detached: the app holding
 * the agent closed its socket mid-call, so nothing was rendering the prompt or answering a tool —
 * both are nobody's fault and neither is an error.
 */
export const EndReasonSchema = z.enum(["caller_hung_up", "agent_hung_up", "supervisor_ended", "transferred", "no_answer", "busy", "dial_failed", "timeout", "drained", "app_detached", "error"]);

/** Whose action ended the call. platform covers timeouts, errors and a drained worker. */
export const EndedBySchema = z.enum(["caller", "agent", "supervisor", "platform"]);

/**
 * What one judge answered about a finished call. Held: the rule held. Broken: it did not, and the
 * reason names the evidence. Classified: a judge that picks a choice or gives a score answered, in
 * `choice` or `score`. N/A: the question did not apply to this call, never billed. Deferred: the
 * judge was asked and could not settle it. Skipped: nobody asked it — no model was reachable, the
 * call's judging ceiling was reached, or the org's evals for the month are used up.
 */
export const ScoreVerdictSchema = z.enum(["held", "broken", "classified", "na", "deferred", "skipped"]);

/**
 * Cold: the caller is sent on with a REFER on their SIP leg and the call ends here. Warm: the
 * number is dialled into the call's own room, the agent stays on the line until the other side
 * answers and then falls silent; the call ends when either of them hangs up.
 */
export const TransferModeSchema = z.enum(["cold", "warm"]);

/**
 * How the knowledge base reaches the model: retrieved, the platform runs search itself when the
 * caller's turn ends; or tool, the model calls search when it decides to. Either way the chunks
 * arrive as a tool result.
 */
export const DocsModeSchema = z.enum(["retrieved", "tool"]);

/**
 * What the platform believes the person on the line is doing right now. The states are the
 * session's own.
 */
export const UserStateSchema = z.enum(["listening", "speaking", "away"]);

/**
 * What the agent is doing right now, in the session's own words: warming up, waiting, hearing the
 * caller, generating, or playing audio.
 */
export const AgentStateSchema = z.enum(["initializing", "idle", "listening", "thinking", "speaking"]);

/**
 * Who a participant is to the call: the person the agent serves (over SIP or the widget), the
 * agent itself, a supervisor who took a seat in the room, a listener who only hears, or a second
 * SIP leg that room.invite brought in.
 */
export const ParticipantKindSchema = z.enum(["caller", "agent", "supervisor", "listener", "sip"]);

/** What a track carries: a microphone's audio, a camera's video, or a screen share. */
export const TrackKindSchema = z.enum(["audio", "video", "screen"]);

/** Where a track comes from, as livekit's TrackSource names it, in lower case. */
export const TrackSourceSchema = z.enum(["microphone", "camera", "screen_share", "screen_share_audio", "unknown"]);

/**
 * Where an outside fact came from: the tenant's backend over the app socket (app), or a
 * participant's browser over the DataChannel (participant).
 */
export const EventSourceSchema = z.enum(["app", "participant"]);

export type EventSource = z.infer<typeof EventSourceSchema>;

/**
 * Which projection a sink applies before a state or an entry leaves the platform: public for a
 * participant reading its own call, tenant for the tenant's readers. The contract is
 * docs/protocol/projections.md; a client never applies one.
 */
export const ProjectionSchema = z.enum(["public", "tenant"]);

/**
 * Who is on the line, as far as the platform knows. Everything is optional: a web visitor may be
 * nobody yet.
 */
export const ContactSchema = z.strictObject({
  id: z.string().nullish(),
  phone: z.string().nullish(),
  name: z.string().nullish(),
  email: z.string().nullish(),
  external_id: z.string().nullish(),
});

/**
 * One door to an agent: a channel and, for phone and WhatsApp, the number that answers. A number
 * is a route, never an agent.
 */
export const RouteSchema = z.strictObject({
  channel: ChannelSchema,
  number: z.string().nullable(),
  label: z.string().nullish(),
});

/** The human who sent a supervise verb, as the token that let them in names them. */
export const SupervisorSchema = z.strictObject({
  id: z.string(),
  name: z.string().nullish(),
});

export type Supervisor = z.infer<typeof SupervisorSchema>;

/**
 * What came back from running a tool in the app's process. Either an output or an error, never
 * both.
 */
export const ToolResultSchema = z.strictObject({
  call_id: z.string(),
  name: z.string(),
  output: z.unknown().nullish(),
  error: z.string().nullish(),
  summary: z.string().nullish(),
  duration_s: z.number().nullish(),
});

/**
 * One thing remembered about a contact: a sentence, where it came from, and how well it matched
 * when recalled.
 */
export const MemoryFactSchema = z.strictObject({
  id: z.string().nullish(),
  text: z.string(),
  category: z.string().nullish(),
  score: z.number().nullish(),
  source: z.string().nullish(),
});

/**
 * One operation against the contact's memory: a recall during the turn, a remember at hangup, or a
 * forget on request.
 */
export const MemoryOpSchema = z.strictObject({
  op: z.enum(["recall", "remember", "forget"]),
  contact: z.string().nullish(),
  query: z.string().nullish(),
  facts: z.array(MemoryFactSchema),
  took_ms: z.number(),
});

export type MemoryOp = z.infer<typeof MemoryOpSchema>;

/** One chunk of the knowledge base that retrieval put in front of the model for this turn. */
export const DocSourceSchema = z.strictObject({
  id: z.string(),
  base: z.string().nullish(),
  path: z.string(),
  heading: z.string().nullish(),
  score: z.number(),
  excerpt: z.string().nullish(),
});

/**
 * A log written before money in dollars said a sum in euros: the same number, read as dollars and
 * never converted, and the rate it carried dropped — as the runtime reads it (wire/parts.py,
 * wire/scores.py, `AliasChoices`). A log is never rewritten, so its old word is read here, once.
 */
export function inDollars(raw: unknown, said: string, means: string, carried: readonly string[] = []): unknown {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw) || !(said in raw)) return raw;
  const { [said]: sum, ...rest } = raw as Record<string, unknown>;
  for (const word of carried) delete rest[word];
  return means in rest ? rest : { ...rest, [means]: sum };
}

/** One priced line: a model, what was counted, how much, and what it came to. */
const CostRowShape = z.strictObject({
  provider: z.string(),
  model: z.string(),
  unit: z.enum(["input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens", "characters", "audio_seconds", "requests", "session_seconds", "minutes"]),
  quantity: z.number(),
  unit_price_usd: z.number(),
  usd: z.number(),
});

export const CostRowSchema = z.preprocess((raw) => inDollars(raw, "eur", "usd"), CostRowShape);

/** A usage row the price table does not know. It is listed, never priced at zero. */
export const UnpricedRowSchema = z.strictObject({
  provider: z.string(),
  model: z.string(),
});

/**
 * What the call cost in provider fees, informational, in US dollars, the currency providers price
 * in. The runtime never prices commercially; this is the provider's bill as best we know it.
 */
export const CostSchema = z.preprocess(
  (raw) => inDollars(raw, "eur", "usd", ["rate"]),
  z.strictObject({
    usd: z.number(),
    rows: z.array(CostRowSchema),
    unpriced: z.array(UnpricedRowSchema),
  }),
);

export type Cost = z.infer<typeof CostSchema>;

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

