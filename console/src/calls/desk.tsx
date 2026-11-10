/** The supervisor's desk on a live call: listen, whisper, say, take the line, transfer, end, and the caller waiting for a person. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useListen, type Ear } from "@pinecall/core/use-listen";
import { useSupervise, type Supervising } from "@pinecall/core/use-supervise";
import { type AttentionState } from "@pinecall/core/wire/state";
import { ConfirmButton } from "../apps/confirm";
import { Icon } from "../shell/icons";

/** The hold a supervisor has on a call. */
export interface OnTheLine {
  ear: Ear;
  desk: Supervising;
}

/** Joins the room muted as soon as there is one to join. Lives with the call, not with the desk drawn, so folding the details never drops the line. */
export function useLine(call: string, spoken: boolean, joining: boolean): OnTheLine {
  const ear = useListen(call);
  const desk = useSupervise(call, spoken);
  const joined = useRef(false);
  const { join } = ear;
  useEffect(() => {
    if (!joining || joined.current) return;
    joined.current = true;
    void join();
  }, [joining, join]);
  return { ear, desk };
}

// Whisper and say get separate boxes, so a supervisor never has to check a mode before pressing Enter.
function Field({ verb, asks, send, loud = false }: { verb: string; asks: string; send: (text: string) => Promise<void>; loud?: boolean }): ReactNode {
  const [text, setText] = useState("");
  const sending = (): void => {
    if (text.trim() === "") return;
    void send(text);
    setText("");
  };
  return (
    <div className="calls-desk-field">
      <input
        className="app-input"
        value={text}
        placeholder={asks}
        aria-label={asks}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") sending();
        }}
      />
      <button type="button" className={loud ? "calls-solid" : "app-button"} disabled={text.trim() === ""} onClick={sending}>
        {verb}
      </button>
    </div>
  );
}

function Listen({ ear }: { ear: Ear }): ReactNode {
  switch (ear.listening) {
    case "over":
      return null;
    case "off":
    case "failed":
      return (
        <button type="button" className="app-button calls-toggle" onClick={() => void ear.join()}>
          <Icon name="speaker" size={14} />
          Listen
        </button>
      );
    case "joining":
      return (
        <button type="button" className="app-button calls-toggle" disabled>
          <Icon name="speaker" size={14} />
          Joining…
        </button>
      );
    case "muted":
    case "on": {
      const on = ear.listening === "on";
      return (
        <>
          <button type="button" className={on ? "app-button calls-toggle calls-toggle-on" : "app-button calls-toggle"} aria-pressed={on} onClick={() => ear.hear(!on)}>
            <Icon name="speaker" size={14} />
            {on ? "Listening, mute it" : "Hear it"}
          </button>
          <button type="button" className="app-button calls-toggle" onClick={() => void ear.leave()}>
            Stop
          </button>
        </>
      );
    }
  }
}

export function Desk({ line, spoken, asked }: { line: OnTheLine; spoken: boolean; /** The agent's pending request for a person; taking the line answers it. */ asked: AttentionState | null }): ReactNode {
  const { ear, desk } = line;
  const [to, setTo] = useState<string | null>(null);
  const waiting = asked?.status === "open";
  const refused = ear.error ?? desk.error;

  const transfer = (): void => {
    if (to === null || to.trim() === "") return;
    void desk.transfer(to.trim());
    setTo(null);
  };

  return (
    <section className="dash-card calls-desk" aria-label="Supervise this call">
      <span className="dash-eyebrow">On the line</span>
      {waiting && asked !== null && (
        <div className="calls-asked" role="status">
          <span className="calls-asked-why">
            The agent asked for a person: <b>{asked.reason}</b>
          </span>
          <span className="dash-quiet">
            {spoken ? "On hold" : "Waiting"}, {asked.wait_s}s. Taking the line answers it.
          </span>
        </div>
      )}
      {spoken && (
        <div className="calls-desk-row">
          <Listen ear={ear} />
        </div>
      )}
      <Field verb="Whisper" asks={`Whisper to the agent. The caller never ${spoken ? "hears" : "reads"} it.`} send={(text) => desk.whisper(text)} />
      <Field verb="Say" asks={`Say it to the caller, ${spoken ? "in the agent's voice" : "as the agent"}, word for word.`} send={(text) => desk.say(text)} loud />
      <div className="calls-desk-row">
        <button
          type="button"
          className={waiting && !desk.holding ? "calls-solid" : desk.holding ? "app-button calls-toggle calls-toggle-on" : "app-button"}
          title={desk.holding ? (spoken ? "The agent hears and speaks again, and your microphone stops." : "The agent answers again.") : spoken ? "Your microphone takes the line and the agent stops speaking." : "You answer from here with Say, and the agent writes nothing more."}
          onClick={() => void (desk.holding ? desk.release() : desk.takeOver())}
        >
          {desk.holding ? "Hand back" : spoken ? "Take the line" : "Take the thread"}
        </button>
        {spoken && to === null && (
          <button type="button" className="app-button" onClick={() => setTo("")}>
            Transfer
          </button>
        )}
        <span className="calls-grow" />
        <ConfirmButton label={spoken ? "End call" : "End thread"} asks="End it?" danger onConfirm={() => void desk.end()} />
      </div>
      {spoken && to !== null && (
        <div className="calls-desk-field">
          <input
            className="app-input"
            autoFocus
            value={to}
            placeholder="+34… then Enter"
            aria-label="The number to transfer to"
            onChange={(event) => setTo(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") transfer();
              if (event.key === "Escape") setTo(null);
            }}
          />
          <button type="button" className="app-button" disabled={to.trim() === ""} onClick={transfer}>
            Transfer
          </button>
          <button type="button" className="app-button" onClick={() => setTo(null)}>
            Cancel
          </button>
        </div>
      )}
      {refused !== null && <p className="app-refused">{refused}</p>}
    </section>
  );
}
