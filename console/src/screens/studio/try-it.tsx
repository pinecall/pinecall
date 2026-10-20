/** Try it: the agent as it was last saved, answering a person who types or talks, or a caller a model plays. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { asking, type TestValues } from "../../lib/test-values";
import { Icon, Segmented } from "../../ui";
import { useRoom } from "../talk";
import { fromRoom, Messages, type Message } from "./messages";
import { Played, Pretend, usePlaying } from "./pretend";
import "./try-it.css";

type How = "type" | "talk";

const HOWS: readonly { value: How; label: ReactNode }[] = [
  {
    value: "type",
    label: (
      <span className="sto-how">
        <Icon name="keyboard" size={14} />
        Type
      </span>
    ),
  },
  {
    value: "talk",
    label: (
      <span className="sto-how">
        <Icon name="mic" size={14} />
        Talk
      </span>
    ),
  },
];

export function TryIt({ agent, release, values, onReset }: { agent: string; release: number; values: TestValues | null; onReset: () => void }): ReactNode {
  const room = useRoom(agent, values);
  const { playing, play, stop } = usePlaying(agent);
  const [how, setHow] = useState<How>("type");
  const [over, setOver] = useState(false);
  const [text, setText] = useState("");
  // What was written before the room was ready: on screen at once, until the room carries it.
  const [queued, setQueued] = useState<string | null>(null);
  const simulating = playing.call !== null && !over;
  const inside = room.phase === "live" || room.phase === "connecting";
  const typed = text.trim() !== "";

  // Another way of speaking is another call: the one open is hung up.
  const pick = (chosen: How): void => {
    if (chosen !== how && inside) void room.close();
    setHow(chosen);
  };

  // The line the room carries is the one the page held: it stops standing in for it.
  const carried = room.lines.some((line) => line.kind === "said" && line.speaker === "user");
  useEffect(() => {
    if (queued !== null && (carried || room.phase === "failed" || room.phase === "ended")) setQueued(null);
  }, [queued, carried, room.phase]);

  const send = (event: FormEvent): void => {
    event.preventDefault();
    if (!typed || simulating) return;
    const line = text.trim();
    setText("");
    if (room.phase === "live") {
      void room.write(line);
      return;
    }
    // Shown at once whatever the room is doing; sent when the agent has opened the call.
    setQueued(line);
    if (room.phase === "connecting") room.hold(line);
    else void room.open(how === "talk" ? "talk" : "chat", line);
  };

  // Reaching for the box is the intent: the room starts opening, so it is open by the time a line is written.
  const warm = (): void => {
    if (how === "type" && room.phase === "idle" && !simulating) void room.open("chat");
  };

  const shown: Message[] = [
    ...(room.phase === "connecting" ? [{ kind: "note" as const, id: "joining", text: "Joining the room…" }] : []),
    ...fromRoom(room.lines),
    ...(queued === null ? [] : [{ kind: "said" as const, id: "queued", who: "caller" as const, text: queued, unsettled: true }]),
  ];

  // Hanging up what is open, and a model left playing, then a chat as empty as at the start.
  const startOver = async (): Promise<void> => {
    await Promise.all([stop(), room.close()]);
    onReset();
  };

  const onVoice = inside && room.mode === "talk";
  return (
    <aside className="sto-chat" aria-label="Try it">
      <div className="sto-chat-head">
        <span className="sto-chat-words">
          <span className="sto-chat-title">Try it</span>
          <span className="sto-chat-under">Answers with release {release}{asking(values) ? " · on test values" : ""}</span>
        </span>
        <Segmented options={HOWS} value={how} onChange={pick} />
        <button type="button" className="sto-icon-button" title="Start over" aria-label="Start over" onClick={() => void startOver()}>
          <Icon name="undo" size={15} />
        </button>
      </div>
      <Pretend agent={agent} playing={playing} onPlay={(persona) => void play(persona)} disabled={inside} />
      {playing.call !== null ? (
        <Played call={playing.call} onOver={setOver} />
      ) : (
        <Messages
          messages={shown}
          empty={
            <div className="sto-hello">
              <span className="sto-hello-icon" aria-hidden>
                <Icon name="chat" size={22} />
              </span>
              <span className="sto-hello-title">Say hi to {agent}</span>
              <span className="sto-hello-under">Talk or type like a real caller would. Nothing here counts as a real call.</span>
            </div>
          }
        />
      )}
      {room.error !== null && <p className="sto-wrong sto-chat-error">{room.error}</p>}
      <div className="sto-dock">
        {how === "talk" && !inside ? (
          <button type="button" className="sto-talk" disabled={simulating} onClick={() => void room.open("talk")}>
            <Icon name="mic" size={16} />
            Start talking
          </button>
        ) : (
          <form className="sto-composer" onSubmit={send}>
            {onVoice && (
              <button type="button" className={room.muted ? "sto-mic sto-mic-off" : "sto-mic"} disabled={room.phase !== "live"} aria-label={room.muted ? "Unmute" : "Mute"} onClick={() => void room.toggleMic()}>
                <Icon name="mic" size={15} />
              </button>
            )}
            <input
              className="sto-write"
              aria-label="Write to the agent"
              value={text}
              disabled={simulating}
              onFocus={warm}
              placeholder={simulating ? `A model is playing ${playing.persona ?? "a caller"}…` : onVoice ? "Type into the call — a number, an address…" : "Type a message…"}
              onChange={(event) => setText(event.target.value)}
            />
            {onVoice && !typed ? (
              <button type="button" className="sto-hangup" aria-label="Hang up" onClick={() => void room.close()}>
                <Icon name="phone" size={15} />
              </button>
            ) : (
              <button type="submit" className="sto-send" aria-label="Send" disabled={!typed || simulating}>
                <Icon name="arrow" size={16} />
              </button>
            )}
          </form>
        )}
      </div>
    </aside>
  );
}
