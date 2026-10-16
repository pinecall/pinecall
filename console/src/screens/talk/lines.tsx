/** The conversation as a chat reads it: the agent's replies as text with a row to judge each, yours in a bubble, each tool as a card, and the box. */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { Icon } from "../../ui";
import { Feedback } from "./feedback";
import { words, type Line, type Mark, type Said, type ToolRun } from "./transcript";

/** Every line so far, scrolled to the last one. */
export function Conversation({ lines }: { lines: Line[] }): ReactNode {
  const stream = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = stream.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [lines]);

  return (
    <div className="talk-stream" ref={stream}>
      <div className="talk-column">
        {lines.map((line) => {
          if (line.kind === "said") return line.speaker === "user" ? <Yours key={line.id} line={line} /> : <Agents key={line.id} line={line} />;
          if (line.kind === "tool") return <ToolCard key={line.id} run={line} />;
          return <MarkLine key={line.id} mark={line} />;
        })}
      </div>
    </div>
  );
}

// A word fades in once, when it arrives — which is when it is spoken. Keyed by position on
// purpose: a word already on screen keeps its key and does not re-animate.
function Words({ line }: { line: Said }): ReactNode {
  return (
    <>
      {words(line.text).map((word, at) => (
        <span className="talk-word" key={at}>
          {word}
        </span>
      ))}
      {!line.final && <span className="talk-cursor" aria-hidden />}
    </>
  );
}

// The agent's reply is the page's own text, as a chat reads it, and once it is settled the row
// under it says whether it was right.
function Agents({ line }: { line: Said }): ReactNode {
  return (
    <div className="talk-reply">
      <p className={line.final ? "talk-reply-text" : "talk-reply-text talk-reply-unsettled"}>
        <Words line={line} />
      </p>
      {line.final && <Feedback text={line.text} />}
    </div>
  );
}

// Written and not on the log yet, the bubble is faint and fills in when its turn lands; spoken and
// not settled by the ear yet, it is in italics until the final transcript replaces it.
function Yours({ line }: { line: Said }): ReactNode {
  const classes = ["talk-bubble"];
  if (line.pending === true) classes.push("talk-bubble-pending");
  if (!line.final) classes.push("talk-bubble-unsettled");
  return (
    <div className="talk-yours">
      <p className={classes.join(" ")}>
        <Words line={line} />
      </p>
    </div>
  );
}

/** One tool the model ran: its name and arguments as code, how it went and how long it took, and its answer folded under it. */
function ToolCard({ run }: { run: ToolRun }): ReactNode {
  const [open, setOpen] = useState(false);
  const args = Object.entries(run.args ?? {});
  return (
    <div className={run.status === "failed" ? "talk-tool talk-tool-failed" : "talk-tool"}>
      <button type="button" className="talk-tool-head" onClick={() => setOpen(!open)} aria-expanded={open} disabled={run.result === null}>
        <span className="talk-tool-icon" aria-hidden>
          <Icon name="sliders" size={13} />
        </span>
        <span className="talk-tool-call">
          <span className="talk-tool-name">{run.name}</span>
          <span className="talk-tool-paren">(</span>
          {args.map(([key, value], index) => (
            <span key={key}>
              <span className="talk-tool-key">{key}</span>=<span className="talk-tool-value">{typeof value === "string" ? `"${value}"` : JSON.stringify(value)}</span>
              {index < args.length - 1 && ", "}
            </span>
          ))}
          <span className="talk-tool-paren">)</span>
        </span>
        <span className={`talk-tool-status talk-tool-status-${run.status}`}>{run.status === "running" ? "running…" : run.status === "ok" ? "✓ ok" : "✗ failed"}</span>
        {run.seconds !== null && <span className="talk-tool-time">{Math.round(run.seconds * 1000)}ms</span>}
        {run.result !== null && <span className={open ? "talk-tool-caret talk-tool-caret-open" : "talk-tool-caret"}>▾</span>}
      </button>
      {open && run.result !== null && (
        <div className="talk-tool-body">
          <span className="talk-tool-label">result</span>
          <pre className="talk-tool-result">{run.result}</pre>
        </div>
      )}
    </div>
  );
}

function MarkLine({ mark }: { mark: Mark }): ReactNode {
  return (
    <div className="talk-note-wrap">
      <span className={`talk-note talk-note-${mark.tone}`}>{mark.text}</span>
    </div>
  );
}

/**
 * The box: a wide pill with what it can do at its right end — the voice button, or the arrow once
 * something is typed, the way a chat's box swaps them. On a voice call what is typed goes into the
 * SAME call the microphone is on — a number, an address, a name nobody can spell out loud.
 */
export function Composer({
  placeholder,
  disabled,
  onWrite,
  lead,
  trail,
}: {
  placeholder: string;
  disabled: boolean;
  onWrite: (text: string) => Promise<void>;
  /** At the pill's left end: the microphone on a voice call. */
  lead?: ReactNode;
  /** At its right end while nothing is typed: the way to call, or to hang up. */
  trail?: ReactNode;
}): ReactNode {
  const [text, setText] = useState("");
  const typed = text.trim() !== "";

  const send = (event: FormEvent): void => {
    event.preventDefault();
    if (!typed || disabled) return;
    setText("");
    void onWrite(text.trim());
  };

  return (
    <form className="talk-composer" onSubmit={send}>
      {lead}
      <input className="talk-write" aria-label="Write to the agent" value={text} disabled={disabled} placeholder={placeholder} onChange={(event) => setText(event.target.value)} />
      {typed ? (
        <button type="submit" className="talk-send" disabled={disabled} aria-label="Send" data-tip="Send">
          <Icon name="arrow" size={17} />
        </button>
      ) : (
        trail
      )}
    </form>
  );
}
