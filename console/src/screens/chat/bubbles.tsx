/** Chat bubbles: user on the right, agent on the left, tool calls between. */

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { rowsOf } from "../call/timeline-rows";
import type { WatchedCall } from "../call/use-watched-call";
import { repliesOf, useRevealed } from "./streaming";

// Within this distance of the bottom, the view keeps auto-scrolling.
const FOLLOWING_PX = 80;

/** A sent message not yet confirmed by the log; shown greyed. */
export interface Pending {
  id: number;
  text: string;
}

/**
 * Turns, tools, the streaming reply and pending sent lines. A streaming reply reveals per frame and
 * continues into its settled bubble without restarting.
 */
export function Bubbles({ watched, pending, onConfirmed }: { watched: WatchedCall; pending: Pending[]; onConfirmed: (text: string) => void }): ReactNode {
  const entries = onceEach(watched.entries);
  const rows = rowsOf(entries, watched.state);
  const { streaming, settled } = repliesOf(entries);
  const box = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  // Replies already logged when the call is opened render whole, without animation.
  const [opened] = useState(() => performance.now());
  const [live, setLive] = useState(false);
  useEffect(() => {
    const later = window.setTimeout(() => setLive(true), 600);
    return () => window.clearTimeout(later);
  }, [opened]);

  // Drop the pending line once its user turn is confirmed.
  const users = rows.filter((row) => row.kind === "turn" && row.turn.role === "user").length;
  useEffect(() => {
    const last = [...rows].reverse().find((row) => row.kind === "turn" && row.turn.role === "user");
    if (last?.kind === "turn") onConfirmed(last.turn.text);
  }, [users]);

  const writing = [...streaming.entries()].filter(([speech]) => !settled.has(speech));
  const thinking = watched.state.agent_state === "thinking" && writing.length === 0;

  // Stick to the bottom as content grows, unless the user scrolled up.
  useLayoutEffect(() => {
    const element = box.current;
    if (element !== null && following.current) element.scrollTop = element.scrollHeight;
  });

  return (
    <div
      className="chat-lines"
      ref={box}
      onScroll={(event) => {
        const element = event.currentTarget;
        following.current = element.scrollHeight - element.scrollTop - element.clientHeight < FOLLOWING_PX;
      }}
    >
      {rows.map((row) => {
        if (row.kind === "turn") {
          const speech = row.turn.speech_id ?? `seq-${String(row.seq)}`;
          return row.turn.role === "agent" ? (
            <AgentBubble key={`turn-${String(row.seq)}`} speech={speech} text={row.turn.text} instant={!live} done />
          ) : (
            <div className="chat-line chat-line-user" key={`turn-${String(row.seq)}`}>
              <span className="chat-bubble chat-bubble-you">{row.turn.text}</span>
            </div>
          );
        }
        if (row.kind === "tool") {
          return (
            <div className="chat-line chat-line-tool" key={`tool-${String(row.seq)}`}>
              <span className={`chat-tool chat-tool-${row.run.status}`}>
                {row.run.name} · {row.run.error ?? row.run.summary ?? (row.run.status === "running" ? "running…" : "done")}
              </span>
            </div>
          );
        }
        return null;
      })}
      {writing.map(([speech, text]) => (
        <AgentBubble key={`writing-${speech}`} speech={speech} text={text} instant={false} done={false} />
      ))}
      {pending.map((line) => (
        <div className="chat-line chat-line-user chat-line-pending" key={`pending-${String(line.id)}`}>
          <span className="chat-bubble chat-bubble-you">{line.text}</span>
        </div>
      ))}
      {thinking && (
        <div className="chat-line chat-line-agent">
          <span className="chat-bubble chat-typing" aria-label="the agent is writing">
            <i />
            <i />
            <i />
          </span>
        </div>
      )}
      {watched.error !== null && <p className="chat-error">{watched.error}</p>}
    </div>
  );
}

/** An agent reply, revealed per frame with a caret while streaming. */
function AgentBubble({ speech, text, instant, done }: { speech: string; text: string; instant: boolean; done: boolean }): ReactNode {
  const shown = useRevealed(speech, text, instant);
  const caught = shown.length >= text.length;
  return (
    <div className="chat-line chat-line-agent">
      <span className="chat-bubble">
        {shown}
        {!(done && caught) && <span className="chat-caret" aria-hidden />}
      </span>
    </div>
  );
}

// Remounts and StrictMode replay the log; dedupe by seq.
function onceEach<T extends { seq: number }>(entries: T[]): T[] {
  const seen = new Set<number>();
  return entries.filter((entry) => (seen.has(entry.seq) ? false : (seen.add(entry.seq), true)));
}
