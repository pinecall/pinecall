/** Talking to one agent from the side panel, by voice over the microphone or in writing, and reading the call as it happens. */

import { useEffect, useState, type ReactNode } from "react";

import { elapsed } from "@pinecall/core/calls";
import { useCall } from "@pinecall/core/use-call";
import { type Entry } from "@pinecall/core/wire/envelope";
import { CallScoreSchema, type CallScore } from "@pinecall/core/wire/events-call";
import { TERMINAL_EVENT } from "@pinecall/core/wire/registry";
import { Icon } from "../shell/icons";
import { SidePanel } from "../ui/side-panel";
import { Composer, Conversation } from "./lines";
import { Orb } from "./orb";
import { useSettingsFollowed } from "./stages";
import { CallSummary, type Followed } from "./summary";
import { useRoom, type Talking } from "./use-room";
import "./talk.css";

const GREETING_WAIT_MS = 5000;

/** The header's button: shows and folds the panel, and stays lit while the panel is open. */
export function TalkButton({ open, onClick }: { open: boolean; onClick: () => void }): ReactNode {
  return (
    <button type="button" className={open ? "app-button talk-button talk-button-on" : "app-button talk-button"} aria-pressed={open} onClick={onClick}>
      <Icon name="chat" size={14} />
      Talk
    </button>
  );
}

/** The panel. The room is keyed by the agent, so another agent opens a new conversation; closing the panel hangs up. Escape does not close it, for it would end a call. */
export function TalkPanel({ agent, onClose }: { agent: string; onClose: () => void }): ReactNode {
  return (
    <SidePanel title={`Talk to ${agent}`} icon="chat" flush closesOnEscape={false} onClose={onClose}>
      <Stage key={agent} agent={agent} />
    </SidePanel>
  );
}

/**
 * A chat window from the first moment, as a messenger's is: the conversation, and the box at the
 * foot of it. Reaching for the box opens a written chat, so the agent has greeted by the time a line
 * is written; the button beside it calls. On a call the same box types into it and the button hangs
 * up. A call that ends stays on the page with its numbers at the foot, and the box starts the next one.
 */
function Stage({ agent }: { agent: string }): ReactNode {
  const live = useRoom(agent);
  useSettingsFollowed(agent, live.call, live.phase === "live");
  const [followed, setFollowed] = useState<Followed | null>(null);
  // What the log said of an earlier call is not this one's.
  const log = followed !== null && followed.call === live.call ? followed : null;
  const over = live.phase === "ended" && live.call !== null;
  const empty = live.lines.length === 0 && (live.phase === "idle" || live.phase === "failed");
  const opening = useOpening(live);
  return (
    <section className="talk-stage" aria-label={`Chat with ${agent}`}>
      {live.phase !== "idle" && <Bar live={live} log={log} />}
      {live.error !== null && <p className="talk-refused">{live.error}</p>}
      {empty ? (
        <div className="talk-empty">
          <span className="talk-empty-title">Say hi to {agent}</span>
          <span>Click the box and it greets you, or call it with the button beside it.</span>
        </div>
      ) : (
        <Conversation
          lines={live.lines}
          after={
            <>
              {opening && (
                <div className="talk-opening" role="status" aria-label={`${agent} is opening the call`}>
                  <span className="talk-dots" aria-hidden>
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              )}
              {live.held !== null && (
                <div className="talk-yours">
                  <p className="talk-bubble talk-bubble-pending">{live.held}</p>
                </div>
              )}
              {over && <CallSummary log={log} />}
            </>
          }
        />
      )}
      <Dock agent={agent} live={live} />
      {live.call !== null && <Follow key={live.call} call={live.call} heard={live.heard} onLog={setFollowed} />}
    </section>
  );
}

/** The bar over the conversation: how the call stands, by voice or in writing, and while it is on, the orb. */
function Bar({ live, log }: { live: Talking; log: Followed | null }): ReactNode {
  const now = useNow(live.phase === "live");
  return (
    <header className="talk-bar">
      <span className={`talk-state talk-state-${live.phase}`}>
        <span className="talk-state-dot" aria-hidden />
        <span className="talk-state-mode">
          <Icon name={live.mode === "talk" ? "numbers" : "chat"} size={13} />
          {live.mode === "talk" ? "Voice" : "Text"}
        </span>
        {standing(live)}
        {live.phase === "live" && <span className="talk-clock">{elapsed(live.since, now)}</span>}
      </span>
      {live.phase === "live" && (
        <span className="talk-bar-right">
          <Orb live={live} agentState={log?.state.agent_state ?? null} />
          {live.mode === "chat" && (
            <button type="button" className="talk-end" onClick={() => void live.close()} aria-label="End the chat" data-tip="End the chat">
              <Icon name="close" size={14} />
            </button>
          )}
        </span>
      )}
    </header>
  );
}

/** The box, and at its ends what the call allows: the voice button, or on a voice call the microphone and hang up. */
function Dock({ agent, live }: { agent: string; live: Talking }): ReactNode {
  const inside = live.phase === "live" || live.phase === "connecting";
  const onVoice = inside && live.mode === "talk";
  // With nothing open, a line starts a written chat and is its first message; inside one, it goes into it.
  const write = async (text: string): Promise<void> => (inside ? live.send(text) : live.open("chat", text));
  // Another way of speaking is another call: a chat open is left for the voice one.
  const call = async (): Promise<void> => {
    if (inside) await live.close();
    await live.open("talk");
  };
  const mic = onVoice && (
    <button type="button" className={live.muted ? "talk-mic talk-mic-off" : "talk-mic"} disabled={live.phase !== "live"} onClick={() => void live.toggleMic()} aria-label={live.muted ? "Unmute" : "Mute"} data-tip={live.muted ? "Unmute" : "Mute"}>
      <span className={live.muted ? "talk-bars" : "talk-bars talk-bars-on"} aria-hidden>
        <span />
        <span />
        <span />
        <span />
      </span>
    </button>
  );
  const end = onVoice ? (
    <button type="button" className="talk-hangup" disabled={live.phase === "connecting"} onClick={() => void live.close()} aria-label="Hang up" data-tip="Hang up">
      <Icon name="numbers" size={15} />
    </button>
  ) : (
    <button type="button" className="talk-voice" disabled={live.phase === "connecting"} onClick={() => void call()} aria-label={`Call ${agent}`} data-tip={`Call ${agent}`}>
      <Icon name="wave" size={16} />
    </button>
  );
  return (
    <div className="talk-dock">
      <Composer placeholder={onVoice ? "Type into the call…" : `Message ${agent}…`} onFocus={() => live.phase === "idle" && void live.open("chat")} onWrite={write} lead={mic} trail={end} />
    </div>
  );
}

// The log reaches the stage through this: it opens the call's stream, hands each entry to the room
// for its marks and turns, and lifts what the log has folded to, rendering nothing.
function Follow({ call, heard, onLog }: { call: string; heard: (entry: Entry) => void; onLog: (log: Followed) => void }): ReactNode {
  const [score, setScore] = useState<CallScore | null>(null);
  const { state } = useCall(call, {
    onEntry(entry) {
      heard(entry);
      if (entry.type === TERMINAL_EVENT) setScore(CallScoreSchema.parse(entry.data));
    },
  });
  useEffect(() => onLog({ call, state, score }), [call, state, score, onLog]);
  return null;
}

// Whether the agent is about to open the call: the room being joined, or joined with nothing said yet. An agent with no greeting is not waited for long.
function useOpening(live: Talking): boolean {
  const silent = live.phase === "live" && !live.lines.some((line) => line.kind === "said" && line.speaker === "agent");
  const [gaveUp, setGaveUp] = useState(false);
  useEffect(() => {
    setGaveUp(false);
    if (!silent) return;
    const wait = window.setTimeout(() => setGaveUp(true), GREETING_WAIT_MS);
    return () => window.clearTimeout(wait);
  }, [silent]);
  return live.phase === "connecting" || (silent && !gaveUp);
}

// How the call stands, in the bar, which is drawn once there is a call.
function standing(live: Talking): string {
  const spoken = live.mode === "talk";
  switch (live.phase) {
    case "idle":
      return "Ready";
    case "connecting":
      return "Joining…";
    case "live":
      return spoken ? (live.muted ? "On a call, muted" : "On a call") : "Writing";
    case "ended":
      return spoken ? "Call ended" : "Chat ended";
    case "failed":
      return "The room did not open";
  }
}

// The clock is the one thing here that moves without the room saying anything.
function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!ticking) return;
    const tick = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(tick);
  }, [ticking]);
  return now;
}
