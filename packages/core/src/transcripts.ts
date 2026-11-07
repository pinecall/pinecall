/** The two voices as a room says them: livekit-agents' transcription streams, read segment by segment — the caller's whole per update, the agent's growing word by word. That pace is the karaoke. */

import { ParticipantKind, type Room, type TextStreamReader } from "livekit-client";

/** Who a line belongs to. The agent is a participant of kind AGENT; everyone else is the caller. */
export type Speaker = "user" | "agent";

/** One segment of speech: grey while `final` is false, solid once the trailer settles it. */
export interface Said {
  kind: "said";
  id: string;
  speaker: Speaker;
  text: string;
  final: boolean;
  /** Written rather than spoken, and not on the log yet: drawn dimmed until its turn.user lands. */
  pending?: boolean;
  /** The log has closed the caller's turn this line stands for: its words are the turn's own. */
  landed?: boolean;
}

// Both sides of the conversation arrive from the room on this topic, as livekit-agents publishes
// them: the caller's transcript as one whole stream per STT update, the agent's as one stream per
// sentence written in deltas at the pace the voice is synthesised.
export const TRANSCRIPTION_TOPIC = "lk.transcription";
export const SEGMENT_ID = "lk.segment_id";
export const TRANSCRIPTION_FINAL = "lk.transcription_final";

/** Add or replace one line by id, keeping first-arrival order — a transcript is never reordered. */
export function upsert<T extends { id: string }>(lines: T[], line: T): T[] {
  const at = lines.findIndex((row) => row.id === line.id);
  if (at === -1) return [...lines, line];
  const next = lines.slice();
  next[at] = line;
  return next;
}

/** Read the room's transcripts from now on, each segment said as it grows. Registered BEFORE the room is joined: a handler registered after connect misses the first words. */
export function followTranscripts(room: Room, said: (line: Said) => void): void {
  room.registerTextStreamHandler(TRANSCRIPTION_TOPIC, (reader, from) => {
    void spoken(room, reader, from.identity, said);
  });
}

// One segment from its first delta to the trailer that settles it. A segment's line is the text
// of the most recent stream carrying its id: the caller's final replaces the interim, the agent's
// single stream grows word by word. `attributes` tells the truth about `final` only after the
// iteration ends — during the loop it always says "false".
async function spoken(room: Room, reader: TextStreamReader, identity: string, said: (line: Said) => void): Promise<void> {
  const id = reader.info.attributes?.[SEGMENT_ID] ?? reader.info.id;
  const speaker: Speaker = room.remoteParticipants.get(identity)?.kind === ParticipantKind.AGENT ? "agent" : "user";
  let text = "";
  for await (const chunk of reader) {
    text += chunk;
    said({ kind: "said", id, speaker, text, final: false });
  }
  said({ kind: "said", id, speaker, text, final: reader.info.attributes?.[TRANSCRIPTION_FINAL] === "true" });
}
