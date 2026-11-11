/** The conversation as a chat reads it: the agent's replies lit as they are said; yours in a bubble as the ear hears it; each tool as a card drawing what it answered; and the box. */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { Icon } from "../shell/icons";
import { LagBar, type Lag } from "./lag";
import { shapeOf } from "./tool-shape";
import { ToolView } from "./tool-view";
import { words, type Line, type Mark, type Said, type ToolRun } from "./transcript";

// How close to the end counts as reading the end: a person who scrolled up to read is left alone.
const NEAR_THE_END_PX = 80;

/** Every line so far, each reply with the wait the session measured for it, and what follows the last one (the card of a call that is over), kept in view while the reader is at the end. */
export function Conversation({ lines, lags, after }: { lines: Line[]; lags?: ReadonlyMap<string, Lag>; after?: ReactNode }): ReactNode {
  const stream = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  useEffect(() => {
    const box = stream.current;
    if (box && following.current) box.scrollTop = box.scrollHeight;
  }, [lines, lags, after]);

  return (
    <div
      className="talk-stream"
      ref={stream}
      onScroll={(event) => {
        const box = event.currentTarget;
        following.current = box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_THE_END_PX;
      }}
    >
      <div className="talk-column">
        {lines.map((line) => {
          if (line.kind === "said") return line.speaker === "user" ? <Yours key={line.id} line={line} /> : <Agents key={line.id} line={line} lag={lags?.get(line.id)} />;
          if (line.kind === "tool") return <ToolCard key={line.id} run={line} />;
          return <MarkLine key={line.id} mark={line} />;
        })}
        {after}
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

function Copy({ text }: { text: string }): ReactNode {
  const [copied, setCopied] = useState(false);
  const copy = async (): Promise<void> => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <button type="button" className="talk-copy" onClick={() => void copy()} data-tip={copied ? "Copied" : "Copy"} aria-label="Copy the reply">
      <Icon name={copied ? "check" : "copy"} size={14} />
    </button>
  );
}

// The agent's reply is the page's own text, as a chat reads it. While it is being said each word
// lights as it arrives — the room sends it at the pace the voice says it.
function Agents({ line, lag }: { line: Said; lag?: Lag | undefined }): ReactNode {
  return (
    <div className="talk-reply">
      <p className="talk-reply-text">
        <Words line={line} />
      </p>
      {lag !== undefined && <LagBar lag={lag} />}
      {line.final && <Copy text={line.text} />}
    </div>
  );
}

// Written and not on the log yet, the bubble is faint and fills in when its turn lands. Spoken, it
// is what the ear hears this instant — dim, with the ear's three dots — until the stretch is heard
// to the end; when the log closes the turn, the turn's own words take its place in the same bubble.
function Yours({ line }: { line: Said }): ReactNode {
  const classes = ["talk-bubble"];
  if (line.pending === true) classes.push("talk-bubble-pending");
  if (!line.final) classes.push("talk-bubble-hearing");
  return (
    <div className="talk-yours">
      <p className={classes.join(" ")}>
        {line.final ? line.text : <Words line={{ ...line, final: true }} />}
        {!line.final && (
          <span className="talk-dots" aria-hidden>
            <i />
            <i />
            <i />
          </span>
        )}
      </p>
    </div>
  );
}

/**
 * One tool the model ran: its name and arguments as code, how it went and how long it took, what
 * it answered drawn as what it means when its shape says (a list, a record, a long text), and the
 * answer itself folded under it.
 */
function ToolCard({ run }: { run: ToolRun }): ReactNode {
  const [open, setOpen] = useState(false);
  const args = Object.entries(run.args ?? {});
  const shape = run.status === "ok" ? shapeOf(run.output) : null;
  return (
    <div className={`talk-tool talk-tool-${run.status}`}>
      <button type="button" className="talk-tool-head" onClick={() => setOpen(!open)} aria-expanded={open} disabled={run.result === null}>
        <span className="talk-tool-icon" aria-hidden>
          <Icon name="tools" size={13} />
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
      {shape !== null && (
        <div className="talk-tool-view">
          <ToolView shape={shape} />
        </div>
      )}
      {open && run.result !== null && <pre className="talk-tool-result">{run.result}</pre>}
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
  onFocus,
  onWrite,
  lead,
  trail,
}: {
  placeholder: string;
  onFocus: () => void;
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
    if (!typed) return;
    setText("");
    void onWrite(text.trim());
  };

  return (
    <form className="talk-composer" onSubmit={send}>
      {lead}
      <input className="talk-write" aria-label="Write to the agent" value={text} placeholder={placeholder} onFocus={onFocus} onChange={(event) => setText(event.target.value)} />
      {typed ? (
        <button type="submit" className="talk-send" aria-label="Send" data-tip="Send">
          <Icon name="arrow" size={16} />
        </button>
      ) : (
        trail
      )}
    </form>
  );
}
