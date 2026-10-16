/** The room's facts: who joined, who left, what they published. */

import { z } from "zod";
import {
  ChannelSchema,
  EventSourceSchema,
  ParticipantKindSchema,
  TrackKindSchema,
  TrackSourceSchema,
} from "./defs.js";

/**
 * The LiveKit room exists and the call lives in it. Phone and web calls have one; a text session
 * has no room and never logs this.
 */
export const RoomOpenedSchema = z.strictObject({
  name: z.string(),
  sid: z.string(),
  channel: ChannelSchema,
});

/**
 * Somebody joined the room: the caller over SIP or the widget, the agent, a supervisor, a
 * listener, or a second SIP leg. Their attributes travel verbatim: the caller's number is a fact
 * of the room, not a field we invent.
 */
export const ParticipantJoinedSchema = z.strictObject({
  identity: z.string(),
  kind: ParticipantKindSchema,
  name: z.string().nullish(),
  attributes: z.record(z.string(), z.unknown()),
});

export type ParticipantJoined = z.infer<typeof ParticipantJoinedSchema>;

/** Somebody left the room. When it is the caller, call.ended follows. */
export const ParticipantLeftSchema = z.strictObject({
  identity: z.string(),
  reason: z.string(),
});

/**
 * The room's own voice activity for one participant flipped. Ephemeral: it is a light for the
 * console, and the turns say who spoke.
 */
export const ParticipantSpeakingSchema = z.strictObject({
  identity: z.string(),
  speaking: z.boolean(),
});

/** A participant put a track on the room: their microphone, their camera, a screen. */
export const TrackPublishedSchema = z.strictObject({
  identity: z.string(),
  kind: TrackKindSchema,
  source: TrackSourceSchema,
});

/**
 * A participant's track left the room: they stopped sharing, or a participant.mute took their
 * audio away.
 */
export const TrackUnpublishedSchema = z.strictObject({
  identity: z.string(),
  kind: TrackKindSchema,
  source: TrackSourceSchema,
});

/**
 * A fact arrived from outside the conversation: the tenant's backend sent call.event, or a
 * participant's browser sent pinecall.event. One event for both, told apart by source. It reached
 * the log only because the agent declared the name in its events, from that source; anything else
 * was refused before this.
 */
export const EventReceivedSchema = z.strictObject({
  name: z.string(),
  data: z.record(z.string(), z.unknown()),
  source: EventSourceSchema,
  identity: z.string().nullish(),
});

/**
 * The agent pushed a payload to a browser in the room, on the tenant's room.send. Ephemeral, and
 * the payload stays out of the log: the tenant chose what to send and to whom.
 */
export const RoomSentSchema = z.strictObject({
  topic: z.string(),
  to: z.string().nullish(),
  bytes: z.int(),
});
