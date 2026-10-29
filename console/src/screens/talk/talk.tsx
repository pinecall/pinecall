/** Chat: a human reaches the agent from this tab — by voice over the microphone, or in writing — and reads the call as it happens. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { TERMINAL_EVENT } from "@pinecall/core/wire/registry";
import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router";

import { elapsed } from "@pinecall/core/calls";
import { useCall } from "@pinecall/core/use-call";
import { asking, said, type TestValues } from "../../lib/test-values";
import { Icon, Refused, usePane } from "../../ui";
import { scoreIn } from "../call/over";
import { TestValuesPanel } from "../settings";
import { Inspector } from "./inspector";
import { Composer, Conversation } from "./lines";
import { Orb } from "./orb";
import { CallSummary, type Followed } from "./summary";
import { useRoom, type Talking } from "./use-room";
import "./talk.css";

/**
 * The screen is a chat window from the first moment, as a messenger's is: the conversation, and the
 * box at the foot of it. Writing into the box with nothing open starts a written chat and sends the
 * line; the phone beside it calls. On a call the same box types into it — a number, an address —
 * and the phone hangs up. A thin bar says how the call stands, its orb who is making a sound; a call
 * that ends stays on the page with its numbers at the foot and its own page one click away, and the
 * box starts the next one.
 */
export function Talk(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  // The voice and models this room is tried with, other than the agent's own: asked for here, kept nowhere.
  const [tried, setTried] = useState<TestValues | null>(null);
  const [tuning, setTuning] = useState(false);
  const live = useRoom(agent, tried);
  const pane = usePane({ name: "agent.inspector", initial: 330, min: 260, max: 620, side: "right" });

  return (
    <div className="talk-grid" style={pane.style}>
      {pane.handle}
      <Stage
        agent={agent}
        live={live}
        tune={
          <>
            <button type="button" className={asking(tried) ? "talk-tune talk-tune-on" : "talk-tune"} onClick={() => setTuning((was) => !was)} title={asking(tried) ? said(tried) : "Try another voice or model in this room"}>
              <Icon name="sliders" size={14} />
              {asking(tried) ? "Test values" : "Voice & models"}
            </button>
            {tuning && <TestValuesPanel agent={agent} values={tried} onApply={setTried} onClose={() => setTuning(false)} />}
          </>
        }
      />
      <Inspector call={live.call} />
    </div>
  );
}

/** The conversation and its box, over the room it is handed: the Playground's, and Studio's preview beside its form. The stage carries the agent's state as the log says it (`data-agent-state`), for whatever drives the call from outside. */
export function Stage({ agent, live, tune }: { agent: string; live: Talking; tune?: ReactNode }): ReactNode {
  const [followed, setFollowed] = useState<Followed | null>(null);
  // What the log said of an earlier call is not this one's.
  const log = followed !== null && followed.call === live.call ? followed : null;
  const over = live.phase === "ended" && live.call !== null;
  // Nothing said yet and no call: the heading and the box sit in the middle, as a chat opens.
  const fresh = live.lines.length === 0 && live.phase !== "live" && !over;
  return (
    <section className={fresh ? "talk-stage talk-stage-fresh" : "talk-stage"} aria-label={`Chat with ${agent}`} data-agent-state={log?.state.agent_state ?? undefined}>
      {live.phase !== "idle" && <Bar live={live} log={log} />}
      <Refused>{live.error}</Refused>
      {fresh ? (
        <div className="talk-hello">
          <h2 className="talk-hello-title">{live.phase === "connecting" ? "Joining the room…" : `What should ${agent} help with?`}</h2>
          <Dock agent={agent} live={live} />
        </div>
      ) : (
        <>
          <Conversation lines={live.lines} after={over && live.call !== null ? <CallSummary call={live.call} log={log} /> : undefined} />
          <Dock agent={agent} live={live} />
        </>
      )}
      {live.call !== null && <Follow key={live.call} call={live.call} heard={live.heard} onLog={setFollowed} />}
      {tune}
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
          <Icon name={live.mode === "talk" ? "phone" : "chat"} size={13} />
          {live.mode === "talk" ? "Voice" : "Text"}
        </span>
        {standing(live)}
        {live.phase === "live" && <span className="talk-clock">{elapsed(live.since, now)}</span>}
      </span>
      {live.phase === "live" && <Orb live={live} agentState={log?.state.agent_state ?? null} />}
    </header>
  );
}

/** The box, and at its ends what the call allows: the voice button, or on a voice call the microphone and hang up. */
function Dock({ agent, live }: { agent: string; live: Talking }): ReactNode {
  const inside = live.phase === "live" || live.phase === "connecting";
  const onVoice = inside && live.mode === "talk";
  // With nothing open, a line starts a written chat and is its first message; inside one, it goes into it.
  const write = async (text: string): Promise<void> => (inside ? live.write(text) : live.open("chat", text));
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
  const end = inside ? (
    <button type="button" className="talk-hangup" disabled={live.phase === "connecting"} onClick={() => void live.close()} aria-label={onVoice ? "Hang up" : "End the chat"} data-tip={onVoice ? "Hang up" : "End the chat"}>
      <Icon name="phone" size={16} />
    </button>
  ) : (
    <button type="button" className="talk-voice" onClick={() => void live.open("talk")} aria-label={`Call ${agent}`} data-tip={`Call ${agent} — your microphone, its voice`}>
      <Icon name="wave" size={17} />
    </button>
  );
  return (
    <div className="talk-dock">
      <Composer placeholder={onVoice ? "Type into the call — a number, an address…" : `Message ${agent}…`} disabled={live.phase === "connecting"} onWrite={write} lead={mic} trail={end} />
    </div>
  );
}

// The log reaches the stage through this: it opens the call's stream, hands each entry to the room
// for its marks and turns, and lifts what the log has folded to — the agent's state for the orb, the
// numbers and the verdicts for the card at the foot — rendering nothing. The Inspector opens its
// own, so the two never share a reader.
function Follow({ call, heard, onLog }: { call: string; heard: (entry: Entry) => void; onLog: (log: Followed) => void }): ReactNode {
  const [sealed, setSealed] = useState<Entry | null>(null);
  const { state } = useCall(call, {
    onEntry(entry) {
      heard(entry);
      if (entry.type === TERMINAL_EVENT) setSealed(entry);
    },
  });
  useEffect(() => onLog({ call, state, score: sealed === null ? null : scoreIn([sealed]) }), [call, state, sealed, onLog]);
  return null;
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
      return spoken ? (live.muted ? "On a call · muted" : "On a call") : "Writing";
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
