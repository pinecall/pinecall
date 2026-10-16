/** LiveKit in a test: a room that connects when it is told to, and events the test fires by hand. */

import type { LivekitModule, SeatLocal, SeatParticipant, SeatRoom, SeatTrack } from "../src/seat/livekit.js";

interface RoomEvents {
  trackSubscribed: (track: SeatTrack) => void;
  trackUnsubscribed: (track: SeatTrack) => void;
  disconnected: () => void;
  audioPlaybackChanged: (playing: boolean) => void;
  activeSpeakersChanged: (speakers: SeatParticipant[]) => void;
}

/** A remote audio or video track. Attaching one makes a real element, so it runs on happy-dom only. */
export class FakeTrack implements SeatTrack {
  readonly kind: string;
  attached: HTMLMediaElement[] = [];

  constructor(kind: "audio" | "video") {
    this.kind = kind;
  }

  attach(): HTMLMediaElement {
    const element = document.createElement("audio");
    this.attached.push(element);
    return element;
  }

  detach(): HTMLMediaElement[] {
    const elements = this.attached;
    this.attached = [];
    return elements;
  }
}

/** The page's own participant: records what the seat asked of it. */
export class FakeLocal implements SeatLocal {
  readonly identity = "web_visitor";
  audioLevel = 0;
  readonly microphone: boolean[] = [];
  readonly sent: { text: string; topic: string }[] = [];
  readonly published: { data: string; topic: string }[] = [];
  refuseMicrophone: Error | null = null;

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    if (this.refuseMicrophone !== null) throw this.refuseMicrophone;
    this.microphone.push(enabled);
  }

  async sendText(text: string, options: { topic: string }): Promise<void> {
    this.sent.push({ text, topic: options.topic });
  }

  async publishData(data: Uint8Array, options: { topic: string; reliable: boolean }): Promise<void> {
    this.published.push({ data: new TextDecoder().decode(data), topic: options.topic });
  }
}

/** One fake livekit-client. `load` is what `room({ livekit })` takes. */
export class FakeLivekit {
  readonly rooms: FakeRoom[] = [];
  loads = 0;
  refuseConnect: Error | null = null;
  refuseMicrophone: Error | null = null;
  canPlaybackAudio = true;
  /** When set, a connect waits for it: the seat is still joining. */
  stallConnect: Promise<void> | null = null;
  /** When set, a disconnect waits for it: a network that has gone. */
  stallDisconnect: Promise<void> | null = null;
  readonly journal: string[];
  readonly module: LivekitModule;

  constructor(journal: string[] = []) {
    this.journal = journal;
    const world = this;
    this.module = {
      Room: class extends FakeRoom {
        constructor() {
          super(world);
        }
      },
      RoomEvent: {
        TrackSubscribed: "trackSubscribed",
        TrackUnsubscribed: "trackUnsubscribed",
        Disconnected: "disconnected",
        AudioPlaybackStatusChanged: "audioPlaybackChanged",
        ActiveSpeakersChanged: "activeSpeakersChanged",
      },
      Track: { Kind: { Audio: "audio" } },
    };
  }

  readonly load = async (): Promise<LivekitModule> => {
    this.loads += 1;
    return this.module;
  };

  /** The room the seat made last. */
  get room(): FakeRoom {
    const made = this.rooms.at(-1);
    if (made === undefined) throw new Error("no room was made");
    return made;
  }
}

export class FakeRoom implements SeatRoom {
  readonly localParticipant = new FakeLocal();
  canPlaybackAudio: boolean;
  connected = false;
  disconnects = 0;
  audioStarts = 0;
  readonly #world: FakeLivekit;
  readonly #heard: { [E in keyof RoomEvents]: RoomEvents[E][] } = {
    trackSubscribed: [],
    trackUnsubscribed: [],
    disconnected: [],
    audioPlaybackChanged: [],
    activeSpeakersChanged: [],
  };

  constructor(world: FakeLivekit) {
    this.#world = world;
    this.canPlaybackAudio = world.canPlaybackAudio;
    this.localParticipant.refuseMicrophone = world.refuseMicrophone;
    world.rooms.push(this);
  }

  on<E extends keyof RoomEvents>(event: E, listener: RoomEvents[E]): this {
    this.#heard[event].push(listener);
    return this;
  }

  async connect(url: string, token: string): Promise<void> {
    this.#world.journal.push(`connect ${url} ${token}`);
    await this.#world.stallConnect;
    if (this.#world.refuseConnect !== null) throw this.#world.refuseConnect;
    this.connected = true;
  }

  // LiveKit says Disconnected for a leave the page asked for too; the seat has to tell them apart.
  async disconnect(): Promise<void> {
    this.disconnects += 1;
    await this.#world.stallDisconnect;
    if (!this.connected) return;
    this.connected = false;
    this.hangUp();
  }

  async startAudio(): Promise<void> {
    this.audioStarts += 1;
    this.canPlaybackAudio = true;
  }

  /** The room closed from the other side. */
  hangUp(): void {
    this.connected = false;
    for (const listener of this.#heard.disconnected) listener();
  }

  subscribe(track: SeatTrack): void {
    for (const listener of this.#heard.trackSubscribed) listener(track);
  }

  unsubscribe(track: SeatTrack): void {
    for (const listener of this.#heard.trackUnsubscribed) listener(track);
  }

  speakers(speakers: SeatParticipant[]): void {
    for (const listener of this.#heard.activeSpeakersChanged) listener(speakers);
  }

  /** The browser changed its mind about sound. */
  playback(allowed: boolean): void {
    this.canPlaybackAudio = allowed;
    for (const listener of this.#heard.audioPlaybackChanged) listener(allowed);
  }
}
