/** The one door to livekit-client: loaded when a seat is taken, and the little of it the seat uses. */

/** A remote track as the seat handles it: its kind, what it carries, and the element that plays it. */
export interface SeatTrack {
  readonly kind: string;
  /** The agent's voice is its microphone; the hold melody beside it is another source. */
  readonly source: string;
  attach(): HTMLMediaElement;
  detach(): HTMLMediaElement[];
}

/** Somebody in the room: who, and how loud right now (0 to 1). */
export interface SeatParticipant {
  readonly identity: string;
  readonly audioLevel: number;
}

/** The page's own participant: its microphone, the typed lines it sends, and the word it hung up. */
export interface SeatLocal extends SeatParticipant {
  setMicrophoneEnabled(enabled: boolean): Promise<unknown>;
  sendText(text: string, options: { topic: string }): Promise<unknown>;
  publishData(data: Uint8Array, options: { topic: string; reliable: boolean }): Promise<unknown>;
}

/** The room the page joins. Six events are listened to; nothing else of LiveKit's is named. */
export interface SeatRoom {
  readonly localParticipant: SeatLocal;
  readonly canPlaybackAudio: boolean;
  connect(url: string, token: string): Promise<void>;
  disconnect(): Promise<void>;
  startAudio(): Promise<void>;
  on(event: "trackSubscribed", listener: (track: SeatTrack) => void): this;
  on(event: "trackUnsubscribed", listener: (track: SeatTrack) => void): this;
  on(event: "disconnected", listener: () => void): this;
  on(event: "audioPlaybackChanged", listener: (playing: boolean) => void): this;
  on(event: "activeSpeakersChanged", listener: (speakers: SeatParticipant[]) => void): this;
  on(event: "dataReceived", listener: (payload: Uint8Array, from?: SeatParticipant, kind?: unknown, topic?: string) => void): this;
}

/** What `import("livekit-client")` has to offer the seat. A test hands in a fake of this shape. */
export interface LivekitModule {
  Room: new () => SeatRoom;
  RoomEvent: {
    readonly TrackSubscribed: "trackSubscribed";
    readonly TrackUnsubscribed: "trackUnsubscribed";
    readonly Disconnected: "disconnected";
    readonly AudioPlaybackStatusChanged: "audioPlaybackChanged";
    readonly ActiveSpeakersChanged: "activeSpeakersChanged";
    readonly DataReceived: "dataReceived";
  };
  Track: { Kind: { readonly Audio: "audio" }; Source: { readonly Microphone: "microphone" } };
}

// Loaded, not imported: a page that only follows a phone call never downloads a WebRTC stack, and
// a server that imports this package for `mint` never evaluates one.
/** livekit-client, the moment a seat is needed. */
export function loadLivekit(): Promise<LivekitModule> {
  return import("livekit-client");
}
