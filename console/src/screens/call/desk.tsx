/** Supervisor controls for a watched call: listen, whisper, say, take over, transfer, end. */

import { type AttentionState } from "@pinecall/core/wire/state";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useListen, type Ear } from "@pinecall/core/use-listen";
import { useSupervise, type Supervising } from "@pinecall/core/use-supervise";
import { Button, Input } from "../../ui";

// Whisper and say get separate boxes so a supervisor never has to check a mode before pressing Enter.
const ASKS = {
  whisper: (spoken: boolean): string => `Whisper to the agent — the caller never ${spoken ? "hears" : "reads"} it`,
  say: (spoken: boolean): string => `Say it to the caller, ${spoken ? "in the agent's voice" : "as the agent"}, verbatim`,
};

/**
 * Mounting joins the room muted; unmounting leaves it. Results of each action appear in the log.
 * `spoken` is false for text threads (widget chat, WhatsApp): no audio, no transfer, no microphone.
 * `asked` is the agent's pending request for a human; taking the line answers it.
 */
export function Desk({ call, live, spoken, asked = null }: { call: string; live: boolean; spoken: boolean; asked?: AttentionState | null }): ReactNode {
  const ear = useListen(call);
  const desk = useSupervise(call, spoken);
  const joined = useRef(false);

  useEffect(() => {
    if (!live || !spoken || joined.current) return;
    joined.current = true;
    void ear.join();
  }, [live, spoken, ear]);

  const refused = ear.error ?? desk.error;
  return (
    <div className="call-desk" role="group" aria-label="the supervisor's desk">
      {live && asked?.status === "open" && <Asked asked={asked} spoken={spoken} />}
      {spoken && <Listen ear={ear} live={live} />}
      {live ? (
        <Moves desk={desk} spoken={spoken} />
      ) : (
        <span className="call-desk-note">
          {spoken
            ? "The call is over: nothing is left to supervise. Read its log below, or play its recording."
            : "The conversation is over: nothing is left to supervise. Read it below."}
        </span>
      )}
      {refused !== null && <span className="call-desk-refused">{refused}</span>}
    </div>
  );
}

function Asked({ asked, spoken }: { asked: AttentionState; spoken: boolean }): ReactNode {
  return (
    <div className="call-desk-asked" role="status">
      <span className="call-desk-dot call-desk-dot-warm" />
      <span>
        The agent asked for a person: <b>{asked.reason}</b>
      </span>
      <span className="call-desk-waiting">
        {spoken ? "on hold" : "waiting"} · {asked.wait_s}s
      </span>
    </div>
  );
}

// Enter sends from the focused box only. "Say" is the primary action since the caller hears it.
function Line({ verb, asks, send, loud = false }: { verb: string; asks: string; send: (text: string) => Promise<void>; loud?: boolean }): ReactNode {
  const [text, setText] = useState("");
  const sending = (): void => {
    if (text.trim() === "") return;
    void send(text);
    setText("");
  };
  return (
    <div className="call-desk-say">
      <Input
        size="sm"
        className="call-desk-text"
        value={text}
        placeholder={asks}
        aria-label={asks}
        onChange={(typed) => setText(typed.target.value)}
        onKeyDown={(key) => {
          if (key.key === "Enter") sending();
        }}
      />
      <Button size="sm" kind={loud ? "primary" : undefined} disabled={text.trim() === ""} onClick={sending}>
        {verb}
      </Button>
    </div>
  );
}

// States: off, joining, joined muted, joined listening; over, once the door says the call ended.
function Listen({ ear, live }: { ear: Ear; live: boolean }): ReactNode {
  if (!live) return null;
  switch (ear.listening) {
    case "over":
      return null;
    case "off":
    case "failed":
      return (
        <Button size="sm" pill onClick={() => void ear.join()}>
          <span className="call-desk-dot" />
          Listen
        </Button>
      );
    case "joining":
      return (
        <Button size="sm" pill disabled>
          <span className="call-desk-dot call-desk-dot-warm" />
          Joining…
        </Button>
      );
    case "muted":
      return (
        <>
          <Button size="sm" pill onClick={() => ear.hear(true)}>
            <span className="call-desk-dot call-desk-dot-warm" />
            Hear it
          </Button>
          <Button size="sm" pill onClick={() => void ear.leave()}>
            Stop
          </Button>
        </>
      );
    case "on":
      return (
        <>
          <Button size="sm" pill onClick={() => ear.hear(false)}>
            <span className="call-desk-dot call-desk-dot-on" />
            Listening · mute
          </Button>
          <Button size="sm" pill onClick={() => void ear.leave()}>
            Stop
          </Button>
        </>
      );
  }
}

// Transfer and end are irreversible: transfer needs a typed number, end needs a second press.
// Threads have no transfer (the gateway refuses it).
function Moves({ desk, spoken }: { desk: Supervising; spoken: boolean }): ReactNode {
  const [to, setTo] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);

  const sendTransfer = (): void => {
    if (to === null || to.trim() === "") return;
    void desk.transfer(to.trim());
    setTo(null);
  };

  return (
    <>
      <Line verb="Whisper" asks={ASKS.whisper(spoken)} send={(text) => desk.whisper(text)} />
      <Line verb="Say" asks={ASKS.say(spoken)} send={(text) => desk.say(text)} loud />
      <Button
        size="sm"
        className={desk.holding ? "call-desk-holding" : undefined}
        title={
          desk.holding
            ? spoken
              ? "the agent hears and speaks again, and your microphone stops"
              : "the agent answers again"
            : spoken
              ? "your microphone takes the line: the agent stops speaking"
              : "you answer from here with Say: the agent writes nothing more"
        }
        onClick={() => void (desk.holding ? desk.release() : desk.takeOver())}
      >
        {desk.holding ? "Hand back" : spoken ? "Take the line" : "Take the thread"}
      </Button>
      {!spoken ? null : to === null ? (
        <Button size="sm" onClick={() => setTo("")}>
          Transfer
        </Button>
      ) : (
        <>
          <Input
            size="sm"
            className="call-desk-number"
            autoFocus
            value={to}
            placeholder="+34… then Enter"
            onChange={(typed) => setTo(typed.target.value)}
            onKeyDown={(key) => {
              if (key.key === "Enter") sendTransfer();
              if (key.key === "Escape") setTo(null);
            }}
          />
          <Button size="sm" disabled={to.trim() === ""} onClick={sendTransfer}>
            Transfer
          </Button>
          <Button size="sm" onClick={() => setTo(null)}>
            Cancel
          </Button>
        </>
      )}
      <Button
        size="sm"
        kind="danger"
        className={ending ? "call-desk-armed" : undefined}
        onClick={() => {
          if (ending) void desk.end();
          setEnding(!ending);
        }}
        onBlur={() => setEnding(false)}
      >
        {ending ? "End · sure?" : spoken ? "End call" : "End thread"}
      </Button>
    </>
  );
}
