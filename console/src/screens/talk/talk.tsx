/** Chat: a human reaches the agent from this tab — by voice over the microphone, or in writing — and reads the call as it happens. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { elapsed } from "@pinecall/core/calls";
import { useCall } from "@pinecall/core/use-call";
import { Icon, Refused, usePane } from "../../ui";
import { Inspector } from "./inspector";
import { Composer, Conversation } from "./lines";
import { useRoom, type Talking } from "./use-room";
import "./talk.css";

/**
 * The screen is a chat window from the first moment, as a messenger's is: the conversation, and the
 * box at the foot of it. Writing into the box with nothing open starts a written chat and sends the
 * line; the phone beside it calls. On a call the same box types into it — a number, an address —
 * and the phone hangs up. A thin bar says how the call stands; a call that ends stays on the page,
 * its own page one click away, and the box starts the next one.
 */
export function Talk(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const live = useRoom(agent);
  const pane = usePane({ name: "agent.inspector", initial: 330, min: 260, max: 620, side: "right" });
  // Nothing said yet and no call: the heading and the box sit in the middle, as a chat opens.
  const fresh = live.lines.length === 0 && live.phase !== "live";

  return (
    <div className="talk-grid" style={pane.style}>
      {pane.handle}
      <section className={fresh ? "talk-stage talk-stage-fresh" : "talk-stage"} aria-label={`Chat with ${agent}`}>
        {live.phase !== "idle" && <Bar live={live} />}
        <Refused>{live.error}</Refused>
        {fresh ? (
          <div className="talk-hello">
            <h2 className="talk-hello-title">{live.phase === "connecting" ? "Joining the room…" : `What should ${agent} help with?`}</h2>
            <Dock agent={agent} live={live} />
          </div>
        ) : (
          <>
            <Conversation lines={live.lines} />
            <Dock agent={agent} live={live} />
          </>
        )}
        {live.call !== null && <Marks call={live.call} heard={live.heard} />}
      </section>
      <Inspector agent={agent} call={live.call} />
    </div>
  );
}

/** The bar over the conversation: how the call stands, by voice or in writing, and the call's page once it is over. */
function Bar({ live }: { live: Talking }): ReactNode {
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
      {live.phase === "ended" && live.call !== null && (
        <Link to={`/calls/${live.call}`} className="talk-open">
          Open the conversation ↗
        </Link>
      )}
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

// The log's marks reach the conversation through this: it opens the call's stream and renders
// nothing. The Inspector opens its own, so the two never share a reader.
function Marks({ call, heard }: { call: string; heard: (entry: Entry) => void }): ReactNode {
  useCall(call, { onEntry: heard });
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
