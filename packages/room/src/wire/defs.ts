/** The shapes the rest of the wire is made of: channels, parts of a turn, tools, costs. */

import { z } from "zod";

/**
 * The door the public came through: a phone call over SIP, the browser widget over WebRTC, or
 * WhatsApp text.
 */
export const ChannelSchema = z.enum(["phone", "web", "whatsapp"]);

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
 * reason names the evidence. Deferred: the judge was asked and could not settle it. Skipped:
 * nobody asked it — no model was reachable inside the call's judging budget.
 */
export const ScoreVerdictSchema = z.enum(["held", "broken", "deferred", "skipped"]);

/**
 * Cold: the caller is sent on with a REFER on their SIP leg and the call ends here. Warm: the
 * number is dialled into the call's own room, the agent stays on the line until the other side
 * answers and then falls silent; the call ends when either of them hangs up.
 */
export const TransferModeSchema = z.enum(["cold", "warm"]);

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

/** One chunk of the knowledge base that retrieval put in front of the model for this turn. */
export const DocSourceSchema = z.strictObject({
  id: z.string(),
  base: z.string().nullish(),
  path: z.string(),
  heading: z.string().nullish(),
  score: z.number(),
  excerpt: z.string().nullish(),
});

/** One priced line: a model, what was counted, how much, and what it came to. */
export const CostRowSchema = z.strictObject({
  provider: z.string(),
  model: z.string(),
  unit: z.enum(["input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens", "characters", "audio_seconds", "requests", "session_seconds", "minutes"]),
  quantity: z.number(),
  unit_price_usd: z.number(),
  usd: z.number(),
});

/** A usage row the price table does not know. It is listed, never priced at zero. */
export const UnpricedRowSchema = z.strictObject({
  provider: z.string(),
  model: z.string(),
});

/**
 * What the call cost in provider fees, informational, in US dollars, the currency providers price
 * in. The runtime never prices commercially; this is the provider's bill as best we know it.
 */
export const CostSchema = z.strictObject({
  usd: z.number(),
  rows: z.array(CostRowSchema),
  unpriced: z.array(UnpricedRowSchema),
});

