/** The commands an app sends a call, one schema each. */

import { z } from "zod";
import { AgentConfigSchema } from "./agent-config.js";
import {
  ContactSchema,
  RouteSchema,
  SupervisorSchema,
  ToolSpecSchema,
  TransferModeSchema,
} from "./defs.js";
import { VerbSchema } from "./verbs.js";

/**
 * Declare or change what the agent is: voice, models, greeting, the full tool list. Only
 * the fields sent change.
 */
export const AgentConfigureSchema = z.strictObject({
  config: AgentConfigSchema,
});

/** This socket is leaving, and its calls go on without it. */
export const AgentDrainSchema = z.strictObject({});

/**
 * The app's first message: this socket speaks for this agent and answers these doors. The gateway
 * answers agent.registered, or error.
 */
export const AgentRegisterSchema = z.strictObject({
  routes: z.array(RouteSchema),
  sdk: z.string().nullish(),
  host: z.string().nullish(),
  takes_unclaimed: z.boolean().nullish(),
  /** This socket answers the console's dev verbs for the agent; `view.render` still goes to the one serving the call. */
  answers_dev: z.boolean().nullish(),
});

/**
 * Make the model speak now, guided by an instruction it reads and the caller never hears: 'tell
 * them a slot at 10:15 just opened'. On livekit's session.generate_reply; the sibling of
 * agent.say, which speaks verbatim. The reply lands as turn.agent.
 */
export const AgentReplySchema = z.strictObject({
  instructions: z.string(),
  allow_interruptions: z.boolean().nullish(),
});

/**
 * Make the agent say this text now, verbatim, outside the model's turn: a greeting, a read-back, a
 * system notice. The reply lands as turn.agent.
 */
export const AgentSaySchema = z.strictObject({
  text: z.string(),
  allow_interruptions: z.boolean().nullish(),
});

/**
 * Ask for a person without sending the caller anywhere: the call waits on hold until a supervisor
 * takes the line, or until wait_s passes with nobody taking it. attention.answered says which.
 */
export const CallAttentionSchema = z.strictObject({
  reason: z.string(),
  wait_s: z.number(),
});

/**
 * Write down that the caller wants to be called back. Lands as callback.requested with via agent;
 * placing the call is the app's.
 */
export const CallCallbackSchema = z.strictObject({
  number: z.string(),
  when: z.string().nullish(),
  note: z.string().nullish(),
});

/** The caller asked never to be called again: their number joins the org's do-not-call list. */
export const CallOptOutSchema = z.strictObject({
  note: z.string().max(500).nullish(),
});

/** The code the caller said, to bind this call to the page that shows it. */
export const CallClaimSchema = z.strictObject({
  code: z.string().regex(/^[0-9]{4}$/),
});

/**
 * Place an outbound call as this agent. The new call's log opens with call.dialing; call.started
 * follows when the far end answers.
 */
export const CallDialSchema = z.strictObject({
  to: z.string(),
  from: z.string().nullish(),
  caller: ContactSchema.nullish(),
  metadata: z.record(z.string(), z.unknown()).nullish(),
});

/** Send touch tones down the line, for an IVR on the far end. */
export const CallDtmfSchema = z.strictObject({
  digits: z.string(),
});

/**
 * Hand the agent a fact from the tenant's backend: a slot freed, an order shipped, a payment
 * confirmed. Lands as event.received with source app. The agent must have declared the name in its
 * events with app among the senders, or the gateway answers error and nothing touches the log.
 */
export const CallEventSchema = z.strictObject({
  name: z.string(),
  data: z.record(z.string(), z.unknown()),
});

/** End the call from the app's side. call.ended follows with reason agent_hung_up. */
export const CallHangupSchema = z.strictObject({
  reason: z.string().nullish(),
});

/** Put the caller on hold: they hear hold audio, the agent hears nothing. */
export const CallHoldSchema = z.strictObject({});

/**
 * Write a line of the app's own into the call's log. It gets a seq like everything else and lands
 * as custom.
 */
export const CallLogSchema = z.strictObject({
  name: z.string(),
  data: z.record(z.string(), z.unknown()),
});

/** Mute the agent: it keeps listening and thinking, produces no audio. */
export const CallMuteSchema = z.strictObject({});

/**
 * Send the caller to another number, or bring that number into the call. call.transferred says
 * whether it worked, and which mode it was.
 */
export const CallTransferSchema = z.strictObject({
  to: z.string(),
  mode: TransferModeSchema.nullish(),
});

/** Take the caller off hold. */
export const CallUnholdSchema = z.strictObject({});

/** Unmute the agent. */
export const CallUnmuteSchema = z.strictObject({});

/**
 * Why the verb did not run, in the words the console shows: the status it travels under, and the
 * sentence.
 */
export const DevRefusalSchema = z.strictObject({
  status: z.int(),
  detail: z.string(),
});

/** What came of one dev.request, named by its id. */
export const DevAnswerSchema = z.strictObject({
  id: z.string(),
  result: z.record(z.string(), z.unknown()).nullish(),
  refused: DevRefusalSchema.nullish(),
});

/**
 * Silence a participant for the rest of the call: their audio leaves the room, for everyone in it.
 * Lands as track.unpublished for their microphone. There is no unmute; a leg that must speak again
 * is invited again.
 */
export const ParticipantMuteSchema = z.strictObject({
  identity: z.string(),
});

/**
 * Put a participant out of the room. Lands as participant.left with reason participant_removed.
 * Removing the caller ends the call.
 */
export const ParticipantRemoveSchema = z.strictObject({
  identity: z.string(),
});

/** Is the socket alive? The gateway answers pong. */
export const PingSchema = z.strictObject({});

/**
 * Rewrite one block of the prompt, whole, by name. The name must be one of the agent's declared
 * blocks, or one of the default four; anything else is refused with the name.
 */
export const PromptSetSchema = z.strictObject({
  name: z.string(),
  text: z.string(),
});

/**
 * Bring somebody else into the call's room. A second SIP leg dialed to a number is the warm path:
 * the agent stays on with the caller while the other side answers. Lands as participant.joined
 * when they arrive, or error when they do not.
 */
export const RoomInviteSchema = z.strictObject({
  to: z.string(),
  kind: z.enum(["sip", "participant"]),
});

/**
 * Push a payload to a browser in the room over the DataChannel: a card to render, a form to open.
 * Lands as room.sent with the size, never the payload. The widget listens on pinecall.ui; a topic
 * of the tenant's own reaches the tenant's own page code.
 */
export const RoomSendSchema = z.strictObject({
  topic: z.string(),
  data: z.record(z.string(), z.unknown()),
  to: z.string().nullish(),
});

/**
 * Set up this one call before the first turn: the app's initial state, and any config that differs
 * from the agent's defaults for this caller.
 */
export const SessionConfigureSchema = z.strictObject({
  state: z.record(z.string(), z.unknown()).nullish(),
  config: AgentConfigSchema.nullish(),
});

/** The app's state changed and this is all of it. The platform logs state.changed and re-renders. */
export const StateSetSchema = z.strictObject({
  state: z.record(z.string(), z.unknown()),
  changed: z.array(z.string()).nullish(),
});

/** One supervise verb, from the human the door named. */
export const SupervisorVerbSchema = z.strictObject({
  by: SupervisorSchema,
  verb: VerbSchema,
});

/**
 * The tools the model may see now. The full list was declared in agent.configure; this is the
 * subset whose when allows them in this state.
 */
export const ToolsSetSchema = z.strictObject({
  tools: z.array(ToolSpecSchema),
});
