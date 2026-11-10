/** The call read as a trace: each exchange a group of bars on one axis, in seconds from the call's start; a bar picked is read in the details. */

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { blockShapes, headline, readings, seconds } from "@pinecall/core/metrics";
import { Readings, toolReadings } from "./log-rows";
import { type Behind, type Trace, type TraceBar } from "./trace-bars";

// The narrowest a second is drawn: a long call scrolls sideways rather than squeezing a turn to a line.
const PX_PER_SECOND = 24;
const AXIS_STEP_S = 5;
const NEAR_THE_END_PX = 80;

function share(instant: number, span: number): string {
  return `${String((instant / span) * 100)}%`;
}

function Axis({ span }: { span: number }): ReactNode {
  const marks = Array.from({ length: Math.floor(span / AXIS_STEP_S) + 1 }, (_, at) => at * AXIS_STEP_S);
  return (
    <div className="calls-trace-line calls-trace-axis">
      <span className="calls-trace-name" />
      <span className="calls-trace-lane">
        {marks.map((mark) => (
          <span key={mark} className="calls-trace-mark" style={{ left: share(mark, span) }}>
            {mark} s
          </span>
        ))}
      </span>
    </div>
  );
}

function Line({ bar, span, picked, onPick }: { bar: TraceBar; span: number; picked: boolean; onPick: () => void }): ReactNode {
  const length = bar.to - bar.from;
  const kept = length > 0 ? seconds(length) : "";
  return (
    <div className={picked ? "calls-trace-line calls-trace-picked" : "calls-trace-line"}>
      <span className="calls-trace-name dash-clip" title={bar.label}>
        {bar.label}
      </span>
      <span className="calls-trace-lane">
        <button type="button" className={`calls-trace-bar calls-trace-${bar.kind}${bar.cut ? " calls-trace-cut" : ""}`} style={{ left: share(bar.from, span), width: `max(3px, ${share(length, span)})` }} title={`${bar.label}, ${kept === "" ? "no length measured" : kept}`} aria-pressed={picked} onClick={onPick} />
        {bar.tick !== null && <span className="calls-trace-tick" style={{ left: share(bar.tick, span) }} aria-hidden="true" />}
        <span className="calls-trace-took" style={{ left: `calc(${share(bar.to, span)} + 6px)` }}>
          {kept}
        </span>
      </span>
    </div>
  );
}

export function TraceView({ trace, picked, onPick }: { trace: Trace; picked: string | null; onPick: (bar: string | null) => void }): ReactNode {
  const box = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const span = Math.max(trace.span, 1);

  useEffect(() => {
    const here = box.current;
    if (here !== null && following.current) {
      here.scrollTop = here.scrollHeight;
      here.scrollLeft = here.scrollWidth;
    }
  }, [trace]);

  const width = { "--trace-width": `${String(Math.ceil(span * PX_PER_SECOND))}px` } as CSSProperties;
  return (
    <div
      className="calls-trace calls-scroll"
      ref={box}
      onScroll={(event) => {
        const here = event.currentTarget;
        following.current = here.scrollHeight - here.scrollTop - here.clientHeight < NEAR_THE_END_PX && here.scrollWidth - here.scrollLeft - here.clientWidth < NEAR_THE_END_PX;
      }}
    >
      {trace.rows.length === 0 ? (
        <p className="dash-quiet calls-chat-nothing">Nothing measured yet. The first turn fills this in.</p>
      ) : (
        <div className="calls-trace-sheet" style={width}>
          <Axis span={span} />
          {trace.rows.map((row) => (
            <section key={row.speech} className="calls-trace-exchange">
              <div className="calls-trace-said dash-clip">{row.said ?? "—"}</div>
              {row.bars.map((bar) => (
                <Line key={bar.id} bar={bar} span={span} picked={bar.id === picked} onPick={() => onPick(bar.id === picked ? null : bar.id)} />
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function What({ behind }: { behind: Behind }): ReactNode {
  switch (behind.kind) {
    case "block":
      return <Readings rows={readings(behind.at, blockShapes().get(behind.block))} />;
    case "tool":
      return <Readings rows={toolReadings(behind.run)} />;
    case "turn":
      return (
        <>
          <p className="calls-step-said">{behind.turn.text}</p>
          <Readings rows={headline(behind.turn)} />
        </>
      );
  }
}

/** The account of one bar, in the details: the block, the tool or the turn behind it, field by field. */
export function TraceStep({ bar, onClose }: { bar: TraceBar; onClose: () => void }): ReactNode {
  const length = bar.to - bar.from;
  return (
    <section className="dash-card calls-step" aria-label="The step picked in the trace">
      <div className="calls-part-top">
        <span className="dash-eyebrow">Step</span>
        <button type="button" className="calls-link" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="calls-step-head">
        <span className="calls-step-name dash-clip">{bar.label}</span>
        <span className="dash-quiet">
          at {bar.from.toFixed(2)} s{length > 0 && `, ${seconds(length)}`}
          {bar.cut && (bar.kind === "tool" ? ", failed" : bar.kind === "agent" ? ", interrupted" : ", cancelled")}
        </span>
      </div>
      <What behind={bar.behind} />
    </section>
  );
}
