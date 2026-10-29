/** An ear on the agent's voice in the Talk screen's room: how loud it is this instant, for the orb in the bar. */

import { createAudioAnalyser, type RemoteAudioTrack, type RemoteParticipant } from "livekit-client";

/** An ear on the agent's voice: how loud it is this instant, and the way to stop listening. */
export interface Ear {
  track: string | undefined;
  level: () => number;
  stop: () => void;
}

// What the analyser reads from speech sits low in its 0-to-1 range: this brings a spoken syllable
// near the top of it, where the orb swells.
const LOUDNESS = 1.8;

// The level is read from the track itself, every frame it is asked; a browser that cannot analyse
// audio falls back on the level the room reports for the agent, a few times a second.
export function earOn(track: RemoteAudioTrack, agent: RemoteParticipant): Ear {
  try {
    const ear = createAudioAnalyser(track, { smoothingTimeConstant: 0.6 });
    const context = ear.analyser.context;
    if (context instanceof AudioContext && context.state === "suspended") void context.resume();
    return { track: track.sid, level: () => Math.min(1, ear.calculateVolume() * LOUDNESS), stop: () => void ear.cleanup().catch(() => undefined) };
  } catch {
    return { track: track.sid, level: () => agent.audioLevel, stop: () => undefined };
  }
}
