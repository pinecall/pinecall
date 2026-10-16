/** Supervisor controls for a live call: verbs, and the microphone for takeover. */

import { type Verb } from "./wire/verbs.js";
import { Room, Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Credentials } from "./api";
import { useCredentials } from "./credentials";
import { seatIn } from "./seat";
import { sendVerb } from "./verbs";

/** Supervisor actions, whether we hold the line, and the last error. */
export interface Supervising {
  whisper: (text: string) => Promise<void>;
  say: (text: string) => Promise<void>;
  takeOver: () => Promise<void>;
  release: () => Promise<void>;
  transfer: (to: string) => Promise<void>;
  end: () => Promise<void>;
  holding: boolean;
  error: string | null;
}

// Only cold transfer is supported; the door refuses other modes with ONLY_COLD.
const THE_ONLY_MODE = "cold";

/** Supervision of one call: seat, microphone and verbs. A plain class so tests can drive it. */
export class Desk {
  readonly #credentials: Credentials;
  readonly #call: string;
  // False for text threads (chat, WhatsApp): no room, so never request the microphone.
  readonly #spoken: boolean;
  #room: Room | null = null;

  constructor(credentials: Credentials, call: string, spoken: boolean) {
    this.#credentials = credentials;
    this.#call = call;
    this.#spoken = spoken;
  }

  /** Whether the call is spoken. */
  get spoken(): boolean {
    return this.#spoken;
  }

  /** Send one verb on the call. */
  async send(verb: Verb): Promise<void> {
    await sendVerb(this.#credentials, this.#call, verb);
  }

  // `setMicrophoneEnabled` opens and publishes the mic (LocalParticipant.d.ts:100).
  /** Publish the mic (spoken calls only), then send `takeover`. */
  async take(): Promise<void> {
    if (this.#spoken) {
      const room = await this.#seated();
      await room.localParticipant.setMicrophoneEnabled(true);
    }
    await this.send({ verb: "takeover" });
  }

  /** Send `release` and unpublish the mic. */
  async give(): Promise<void> {
    await this.send({ verb: "release" });
    await this.#unpublish();
  }

  /** Unpublish and leave the room. */
  async leave(): Promise<void> {
    await this.#unpublish();
    await this.#room?.disconnect();
    this.#room = null;
  }

  // Minted once and reused: a second token would add a second participant to the room.
  async #seated(): Promise<Room> {
    if (this.#room !== null) {
      return this.#room;
    }
    const seat = await seatIn(this.#credentials, this.#call, "supervise");
    const room = new Room();
    // No subscriptions: audio is played by the listen seat (use-listen.ts); this would double it.
    await room.connect(seat.server_url, seat.participant_token, { autoSubscribe: false });
    this.#room = room;
    return room;
  }

  // Unpublish and stop rather than mute, so the OS recording indicator turns off.
  async #unpublish(): Promise<void> {
    const me = this.#room?.localParticipant;
    const published = me?.getTrackPublication(Track.Source.Microphone);
    if (me === undefined || published?.track === undefined) {
      return;
    }
    await me.unpublishTrack(published.track, true);
  }
}

/** Supervise one call; errors carry the gateway's message. */
export function useSupervise(call: string, spoken: boolean): Supervising {
  const credentials = useCredentials();
  const [holding, setHolding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const desk = useRef<Desk | null>(null);

  // Rebuild when `spoken` changes (a call can become spoken while on screen); the old desk held no room.
  const held = useCallback((): Desk => {
    if (desk.current === null || desk.current.spoken !== spoken) {
      desk.current = new Desk(credentials, call, spoken);
    }
    return desk.current;
  }, [call, credentials, spoken]);

  // `holding` changes only when a takeover or release succeeds.
  const moved = useCallback(
    async (move: (desk: Desk) => Promise<void>, line: boolean | null): Promise<void> => {
      setError(null);
      try {
        await move(held());
        if (line !== null) {
          setHolding(line);
        }
      } catch (refused) {
        setError(refused instanceof Error ? refused.message : String(refused));
      }
    },
    [held],
  );

  const whisper = useCallback((text: string) => moved((desk) => desk.send({ verb: "whisper", text }), null), [moved]);
  const say = useCallback((text: string) => moved((desk) => desk.send({ verb: "say", text }), null), [moved]);
  const takeOver = useCallback(() => moved((desk) => desk.take(), true), [moved]);
  const release = useCallback(() => moved((desk) => desk.give(), false), [moved]);
  const transfer = useCallback(
    (to: string) => moved((desk) => desk.send({ verb: "transfer", to, mode: THE_ONLY_MODE }), null),
    [moved],
  );
  const end = useCallback(() => moved((desk) => desk.send({ verb: "end" }), null), [moved]);

  // Leave the room on unmount.
  useEffect(() => {
    return () => {
      void desk.current?.leave();
      desk.current = null;
    };
  }, []);

  return { whisper, say, takeOver, release, transfer, end, holding, error };
}
