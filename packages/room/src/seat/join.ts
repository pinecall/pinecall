/** A seat in the call's room, talking or typing. The only file that names LiveKit's events. */

import type { LivekitModule, SeatParticipant } from "./livekit.js";
import type { Sink } from "./sink.js";

/** Who is making a sound right now, and how loud the agent is (0 to 1). */
export interface Speaking {
  agent: boolean;
  user: boolean;
  level: number;
}

/** What the seat tells the room about itself after it is taken. */
export interface SeatHears {
  /** The room closed from the other side: the agent hung up, or the network went. */
  disconnected: () => void;
  speaking: (speaking: Speaking) => void;
  /** True when the browser has not been told it may make a sound. */
  wantsSound: (wanted: boolean) => void;
  /** The element the agent's voice plays in, as it arrives; null once it has gone. */
  voice: (element: HTMLMediaElement | null) => void;
  /** What the agent put on the visitor's screen (`pinecall.ui`), decoded; never a line of the conversation. */
  ui: (data: unknown) => void;
}

export interface SeatOptions {
  livekit: LivekitModule;
  server_url: string;
  participant_token: string;
  mode: "talk" | "chat";
  sink: Sink;
  on: SeatHears;
}

/** A taken seat. Leaving is final; `on.disconnected` is not called for a seat that left. */
export interface Seat {
  send(text: string): Promise<void>;
  /** A fact about the page, for the agent's `onEvent`: `{name, data}` on `pinecall.event`. */
  event(name: string, data: Record<string, unknown>): Promise<void>;
  /** Leave, the call going on without the page: a reload looks like this, and the call waits for it. */
  leave(): Promise<void>;
  /** Say the visitor hung up, then leave: the call ends at once instead of waiting for them. */
  hangUp(): Promise<void>;
  playSound(): void;
  canPlaybackAudio(): boolean;
}

/** The topic a typed line rides on. LiveKit's own, and the one the agent listens to. */
const CHAT = "lk.chat";

/** The topic a hang-up is said on: a hang-up and a reload both disconnect the seat alike. */
const HANGUP = "pinecall.hangup";

/** The topic a fact about the page rides on; the runtime hands it to the agent's `onEvent`. */
const EVENT = "pinecall.event";

/** The topic the agent shows things on: `call.send("pinecall.ui", data)`. */
const UI = "pinecall.ui";

/** Join the room. Rejects with the room's own error when it cannot connect or hear the microphone. */
export async function joinSeat(options: SeatOptions): Promise<Seat> {
  const { livekit, mode, sink, on } = options;
  const { RoomEvent } = livekit;
  const room = new livekit.Room();
  let left = false;

  const leave = (): Promise<void> => {
    left = true;
    sink.close();
    return room.disconnect();
  };

  // Chat never plays the agent: a written conversation that starts talking out loud is a bug.
  // Every audio track plays; the voice is the one published as a microphone. The agent's hold
  // melody is a second audio track, and taken for the voice it left the face hearing silence.
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (mode !== "talk" || track.kind !== livekit.Track.Kind.Audio) return;
    const element = track.attach();
    sink.add(element);
    if (track.source === livekit.Track.Source.Microphone) on.voice(element);
  });
  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    const gone = track.detach();
    for (const element of gone) sink.remove(element);
    if (gone.length > 0 && track.source === livekit.Track.Source.Microphone) on.voice(null);
  });
  room.on(RoomEvent.DataReceived, (payload, _from, _kind, topic) => {
    if (topic !== UI) return;
    const data = decoded(payload);
    if (data !== undefined) on.ui(data);
  });
  room.on(RoomEvent.Disconnected, () => {
    if (left) return;
    left = true;
    sink.close();
    on.disconnected();
  });
  room.on(RoomEvent.AudioPlaybackStatusChanged, () => on.wantsSound(!room.canPlaybackAudio));
  room.on(RoomEvent.ActiveSpeakersChanged, (speakers) =>
    on.speaking(speakingOf(speakers, room.localParticipant.identity)),
  );

  try {
    await room.connect(options.server_url, options.participant_token);
    if (mode === "talk") await room.localParticipant.setMicrophoneEnabled(true);
  } catch (refused) {
    // The refusal is the news. A room that also fails to close has nothing to add to it.
    await leave().catch(() => undefined);
    throw refused;
  }

  return {
    async send(text) {
      await room.localParticipant.sendText(text, { topic: CHAT });
    },
    async event(name, data) {
      const packed = new TextEncoder().encode(JSON.stringify({ name, data }));
      await room.localParticipant.publishData(packed, { topic: EVENT, reliable: true });
    },
    leave,
    async hangUp() {
      // Said or not, the seat goes: a network that has gone leaves the call to wait, as for a reload.
      await room.localParticipant
        .publishData(new TextEncoder().encode("{}"), { topic: HANGUP, reliable: true })
        .catch(() => undefined);
      await leave();
    },
    playSound() {
      // A browser that still says no leaves the page asking, rather than silently mute.
      room.startAudio().then(
        () => on.wantsSound(!room.canPlaybackAudio),
        () => on.wantsSound(!room.canPlaybackAudio),
      );
    },
    canPlaybackAudio: () => room.canPlaybackAudio,
  };
}

/** The agent is whoever speaks that is not this page; its level is how loud. */
function speakingOf(speakers: SeatParticipant[], me: string): Speaking {
  const remote = speakers.find((speaker) => speaker.identity !== me);
  return {
    agent: remote !== undefined,
    user: speakers.some((speaker) => speaker.identity === me),
    level: remote?.audioLevel ?? 0,
  };
}

/** A payload as JSON, or undefined when it is not: an agent's bad bytes are not the page's error. */
function decoded(payload: Uint8Array): unknown {
  try {
    return JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return undefined;
  }
}
