/** The talk panel's room: a visit token from the gateway — a voice call or a written chat — and what is said as it is said. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { ParticipantKind, RemoteAudioTrack, Room, RoomEvent, Track, type Participant, type RemoteParticipant, type RemoteTrack } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { doorUrl, post, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { followTranscripts } from "@pinecall/core/transcripts";
import { earOn, type Ear } from "./ear";
import {
  A_BEAT_MS,
  CHAT_TOPIC,
  joined,
  landed,
  markOf,
  upsert,
  type Line,
  type Said,
  type Speaker,
} from "./transcript";

/** Where the conversation stands. `ended` keeps the transcript; `open` starts a new call. */
type Phase = "idle" | "connecting" | "live" | "ended" | "failed";

/**
 * How the room is joined: `talk` with the microphone and the agent's voice, `chat` written — the
 * session then has no ears and no voice, and the agent's words arrive at the pace it writes them.
 */
export type Mode = "talk" | "chat";

/** Who is making a sound on a voice call right now, as the room's own speaker detection says. */
export interface Speaking {
  agent: boolean;
  user: boolean;
}

const QUIET: Speaking = { agent: false, user: false };

/** The room as the screen reads it, and the two things it may do to it. */
export interface Talking {
  phase: Phase;
  mode: Mode;
  call: string | null;
  lines: Line[];
  error: string | null;
  /** When the room was joined, in seconds, for the clock. */
  since: number | null;
  /** Whether the microphone is off, on a voice call. */
  muted: boolean;
  speaking: Speaking;
  /** How loud the agent's voice is this instant, 0 to 1: read once an animation frame, never kept in state. */
  level: () => number;
  /** Join the room; `first`, a line written before there was a room, goes the moment the agent is in it. */
  open: (mode: Mode, first?: string) => Promise<void>;
  close: () => Promise<void>;
  /** The microphone off, or on again: the call goes on either way. */
  toggleMic: () => Promise<void>;
  /** Write a line into the call instead of saying it; until the agent has opened the call it waits, and lands under the greeting. */
  send: (text: string) => Promise<void>;
  /** What was written and is waiting for the agent to finish opening the call. */
  held: string | null;
  /** One entry of the call's log, for the marks the room itself does not carry. */
  heard: (entry: Entry) => void;
}

// What `POST /v1/tokens` answers: LiveKit's two fields, the call the token opens, and the token that reads that call
// for as long as it lasts. The seat's token lives a minute, the time to join.
const MintedSchema = z.object({ server_url: z.string(), participant_token: z.string(), call: z.string(), log_token: z.string() });

/**
 * Speak with one agent from this tab.
 */
export function useRoom(agent: string): Talking {
  const credentials = useCredentials();
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<Mode>("talk");
  const [since, setSince] = useState<number | null>(null);
  const [muted, setMuted] = useState(false);
  const [call, setCall] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState<Speaking>(QUIET);
  const [held, setHeld] = useState<string | null>(null);
  const room = useRef<Room | null>(null);
  const hangUp = useRef<(() => void) | null>(null);
  // The agent's voice, as an ear on its track: what the orb's level is read from.
  const voice = useRef<Ear | null>(null);
  const seen = useRef(new Set<string>());
  // The caller's stretches the log has closed a turn over: a late word of one is not drawn again.
  const closed = useRef(new Set<string>());
  const lastSpoken = useRef<Speaker | null>(null);
  const waiting = useRef<Line[]>([]);
  // The tool cards already placed on screen, by id: where a result goes to fill its call's card in.
  const onScreen = useRef(new Set<string>());
  // A line written before there was a room, and the agent's opening: the line waits for the agent
  // to finish opening the call and is placed after it — sent the moment it arrived, it landed above
  // the greeting and the agent greeted twice, once for the room and once for the "hola" (2026-09-26).
  // An agent with no opening says nothing, and the line goes a beat after the agent is in the room.
  const first = useRef<string | null>(null);
  // Whether the agent has finished opening the call, or was given its beat to.
  const settled = useRef(false);
  const flush = useRef<() => void>(() => undefined);
  const nobodyOpened = useRef<number | null>(null);
  const grace = useRef<number | null>(null);

  // The marks held back are placed at the end, in the order they arrived.
  const place = useCallback((): void => {
    if (grace.current !== null) {
      window.clearTimeout(grace.current);
      grace.current = null;
    }
    const held = waiting.current;
    waiting.current = [];
    for (const line of held) onScreen.current.add(line.id);
    if (held.length > 0) setLines((known) => [...known, ...held]);
  }, []);

  // A new segment of the caller's is placed after the marks that came before it; a new segment
  // of the agent's is placed before them, because they are what that sentence announced.
  const said = useCallback(
    (line: Said): void => {
      if (closed.current.has(line.id)) return;
      if (!seen.current.has(line.id)) {
        seen.current.add(line.id);
        if (line.speaker === "user") place();
        setLines((known) => upsert(known, line));
        lastSpoken.current = line.speaker;
        if (line.speaker === "agent") place();
        // The agent is opening the call: the held line waits for it to finish, not for the beat.
        if (line.speaker === "agent" && nobodyOpened.current !== null) {
          window.clearTimeout(nobodyOpened.current);
          nobodyOpened.current = null;
        }
      } else {
        setLines((known) => upsert(known, line));
      }
      if (line.speaker === "agent" && line.final) flush.current();
    },
    [place],
  );

  const typed = useRef(0);

  // A written line is on screen at once, dimmed, and settles when the log's turn.user carries it.
  // A refusal takes it back and says why.
  const write = useCallback(
    async (text: string): Promise<void> => {
      const joined = room.current;
      if (joined === null) return;
      typed.current += 1;
      const id = `typed-${typed.current}`;
      place();
      setLines((known) => [...known, { kind: "said", id, speaker: "user", text, final: true, pending: true }]);
      lastSpoken.current = "user";
      try {
        await joined.localParticipant.sendText(text, { topic: CHAT_TOPIC });
      } catch (failed) {
        setLines((known) => known.filter((line) => line.id !== id));
        setError(failed instanceof Error ? failed.message : String(failed));
      }
    },
    [place],
  );

  const heard = useCallback(
    (entry: Entry): void => {
      if (entry.type === "turn.user") {
        const said = String((entry.data as Record<string, unknown>)["text"] ?? "").trim();
        setLines((known) => {
          // A written line is settled by its own words; else the turn is what the ear heard, closed.
          const at = known.findIndex((line) => line.kind === "said" && line.pending === true && line.text.trim() === said);
          if (at === -1) {
            const turn = landed(known, said);
            for (const id of turn.replaced) closed.current.add(id);
            return turn.lines;
          }
          const next = known.slice();
          next[at] = { ...(known[at] as Said), pending: false, landed: true };
          return next;
        });
        return;
      }
      const mark = markOf(entry);
      if (mark === null) return;
      // A tool's result finds its call's card — still held back, or already placed — and fills it in.
      if (mark.kind === "tool") {
        const held = waiting.current.findIndex((line) => line.id === mark.id);
        if (held !== -1) {
          waiting.current[held] = joined(waiting.current[held] as typeof mark, mark);
          return;
        }
        if (onScreen.current.has(mark.id)) {
          setLines((known) => known.map((line) => (line.id === mark.id && line.kind === "tool" ? joined(line, mark) : line)));
          return;
        }
      }
      if (lastSpoken.current === "agent") {
        onScreen.current.add(mark.id);
        setLines((known) => [...known, mark]);
        return;
      }
      waiting.current.push(mark);
      if (grace.current !== null) window.clearTimeout(grace.current);
      grace.current = window.setTimeout(place, A_BEAT_MS);
    },
    [place],
  );

  const open = useCallback(async (joining: Mode, written?: string): Promise<void> => {
    setPhase("connecting");
    setMode(joining);
    setMuted(false);
    setSince(null);
    setError(null);
    setLines([]);
    setSpeaking(QUIET);
    voice.current?.stop();
    voice.current = null;
    seen.current.clear();
    closed.current.clear();
    onScreen.current.clear();
    lastSpoken.current = null;
    waiting.current = [];
    first.current = written !== undefined && written.trim() !== "" ? written.trim() : null;
    settled.current = false;
    setHeld(first.current);
    if (nobodyOpened.current !== null) window.clearTimeout(nobodyOpened.current);
    nobodyOpened.current = null;
    // Sent once and only once, the way anything typed is: on screen, then into the room.
    flush.current = () => {
      settled.current = true;
      const waiting = first.current;
      if (waiting === null) return;
      first.current = null;
      setHeld(null);
      if (nobodyOpened.current !== null) window.clearTimeout(nobodyOpened.current);
      nobodyOpened.current = null;
      void write(waiting);
    };
    const agentIn = (): void => {
      if (first.current !== null && nobodyOpened.current === null) nobodyOpened.current = window.setTimeout(() => flush.current(), A_BEAT_MS);
    };
    try {
      const minted = MintedSchema.parse(await post(credentials, "/v1/tokens", { agent, scope: joining }));
      // Said at the gateway before the seat leaves the room, with the call's own token: left unsaid, the call waits
      // five minutes for a caller who is not coming back. `keepalive`, so a closing tab still completes it. The token
      // is the one that reads the call: said with the seat's, a hang-up after the first minute was refused as expired,
      // and the call waited those five minutes all the same (2026-11-12).
      const door = doorUrl(credentials, `/v1/calls/${encodeURIComponent(minted.call)}/hangup`, { token: minted.log_token });
      hangUp.current = () => void fetch(door, { method: "POST", keepalive: true }).catch(() => undefined);
      const joined = new Room();
      room.current = joined;
      // Registered before the room is joined: a handler registered after connect misses the first words.
      followTranscripts(joined, said);
      // A chat hears the room only for its text: no voice is attached, whatever arrives.
      if (joining === "talk") {
        joined.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, _publication, participant: RemoteParticipant) => {
          playAloud(track);
          if (track instanceof RemoteAudioTrack && participant.kind === ParticipantKind.AGENT) {
            voice.current?.stop();
            voice.current = earOn(track, participant);
          }
        });
        joined.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
          const me = joined.localParticipant.identity;
          const now = { agent: speakers.some((one) => one.identity !== me), user: speakers.some((one) => one.identity === me) };
          setSpeaking((was) => (was.agent === now.agent && was.user === now.user ? was : now));
        });
      }
      joined.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach().forEach((element) => element.remove());
        const ear = voice.current;
        if (ear !== null && ear.track === track.sid) {
          ear.stop();
          voice.current = null;
        }
      });
      joined.on(RoomEvent.Disconnected, () => {
        voice.current?.stop();
        voice.current = null;
        setSpeaking(QUIET);
        first.current = null;
        setHeld(null);
        setPhase("ended");
      });
      joined.on(RoomEvent.ParticipantConnected, (participant) => {
        if (participant.kind === ParticipantKind.AGENT) agentIn();
      });
      setCall(minted.call);
      await joined.connect(minted.server_url, minted.participant_token);
      if (joining === "talk") await joined.localParticipant.setMicrophoneEnabled(true);
      setSince(Date.now() / 1000);
      setPhase("live");
      // The agent may have been in the room before this tab.
      if ([...joined.remoteParticipants.values()].some((participant) => participant.kind === ParticipantKind.AGENT)) agentIn();
    } catch (failed) {
      setError(saidBy(failed));
      first.current = null;
      setHeld(null);
      setPhase("failed");
    }
  }, [agent, credentials, said, write]);

  const send = useCallback(
    async (text: string): Promise<void> => {
      if (settled.current) return write(text);
      first.current = first.current === null ? text : `${first.current}\n${text}`;
      setHeld(first.current);
      const joined = room.current;
      const agentIn = joined !== null && [...joined.remoteParticipants.values()].some((participant) => participant.kind === ParticipantKind.AGENT);
      // The agent is in the room and has not begun: it has a beat to, and a greeting under way sends the line when it ends.
      if (agentIn && lastSpoken.current !== "agent" && nobodyOpened.current === null) nobodyOpened.current = window.setTimeout(() => flush.current(), A_BEAT_MS);
    },
    [write],
  );

  const close = useCallback(async (): Promise<void> => {
    hangUp.current?.();
    hangUp.current = null;
    await room.current?.disconnect();
  }, []);

  const toggleMic = useCallback(async (): Promise<void> => {
    const joined = room.current;
    if (joined === null) return;
    await joined.localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  }, [muted]);

  // Closing the panel hangs up: a room nobody is looking at is a call nobody is on.
  useEffect(() => {
    return () => {
      voice.current?.stop();
      hangUp.current?.();
      hangUp.current = null;
      void room.current?.disconnect();
    };
  }, []);

  const level = useCallback((): number => voice.current?.level() ?? 0, []);

  return { phase, mode, call, lines, error, since, muted, speaking, level, open, close, toggleMic, send, held, heard };
}

// The agent's voice arrives as a subscribed audio track; attaching it is what plays it. The
// element lives in the document — a detached one is at the mercy of the browser's autoplay rules —
// but never on screen: audio is not a widget, it is the call.
function playAloud(track: RemoteTrack): void {
  if (track.kind !== Track.Kind.Audio) return;
  const element = track.attach();
  element.style.display = "none";
  document.body.append(element);
}
