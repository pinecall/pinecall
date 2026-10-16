/** The call read as a trace: each exchange a group of bars on one axis in seconds from the call's start. */

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { seconds } from "@pinecall/core/metrics";
import { type Trace, type TraceBar } from "./trace-bars";
import "./trace.css";

// The narrowest a second is drawn: a long call scrolls sideways rather than squeezing a turn to a line.
const PX_PER_SECOND = 24;

// A label on the axis every five seconds: 120 px apart at the narrowest scale.
const AXIS_STEP_S = 5;

// Within this distance of the end, the trace keeps following a live call (as the list does).
const NEAR_THE_END_PX = 80;

/** `picked` is the id of the bar the pane shows; a click on a bar picks it, a click on it again lets it go. */
export function TraceView({
  trace,
  picked,
  onPick,
  after,
}: {
  trace: Trace;
  picked: string | null;
  onPick: (bar: string | null) => void;
  after?: ReactNode;
}): ReactNode {
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
      className="trace"
      ref={box}
      onScroll={(event) => {
        const here = event.currentTarget;
        following.current =
          here.scrollHeight - here.scrollTop - here.clientHeight < NEAR_THE_END_PX &&
          here.scrollWidth - here.scrollLeft - here.clientWidth < NEAR_THE_END_PX;
      }}
    >
      {trace.rows.length === 0 ? (
        <div className="trace-nothing">Nothing measured yet: the first turn fills this in.</div>
      ) : (
        <div className="trace-sheet" style={width}>
          <Axis span={span} />
          {trace.rows.map((row) => (
            <section key={row.speech} className="trace-exchange">
              <div className="trace-said">{row.said ?? "—"}</div>
              {row.bars.map((bar) => (
                <Line key={bar.id} bar={bar} span={span} picked={bar.id === picked} onPick={() => onPick(bar.id === picked ? null : bar.id)} />
              ))}
            </section>
          ))}
        </div>
      )}
      {after}
    </div>
  );
}

function Axis({ span }: { span: number }): ReactNode {
  const marks = Array.from({ length: Math.floor(span / AXIS_STEP_S) + 1 }, (_, at) => at * AXIS_STEP_S);
  return (
    <div className="trace-line trace-axis">
      <span className="trace-name" />
      <span className="trace-lane">
        {marks.map((mark) => (
          <span key={mark} className="trace-mark" style={{ left: share(mark, span) }}>
            {mark} s
          </span>
        ))}
      </span>
    </div>
  );
}

// One bar on its own line: its name, then the bar placed on the call's axis and how long it took.
function Line({ bar, span, picked, onPick }: { bar: TraceBar; span: number; picked: boolean; onPick: () => void }): ReactNode {
  const length = bar.to - bar.from;
  const kept = length > 0 ? seconds(length) : "";
  return (
    <div className={picked ? "trace-line trace-picked" : "trace-line"}>
      <span className="trace-name" title={bar.label}>
        {bar.label}
      </span>
      <span className="trace-lane">
        <button
          type="button"
          className={`trace-bar trace-${bar.kind}${bar.cut ? " trace-cut" : ""}`}
          style={{ left: share(bar.from, span), width: `max(3px, ${share(length, span)})` }}
          title={`${bar.label} · ${kept === "" ? "no length measured" : kept}`}
          aria-pressed={picked}
          onClick={onPick}
        />
        {bar.tick !== null && <span className="trace-tick" style={{ left: share(bar.tick, span) }} aria-hidden />}
        <span className="trace-took" style={{ left: `calc(${share(bar.to, span)} + 6px)` }}>
          {kept}
        </span>
      </span>
    </div>
  );
}

function share(instant: number, span: number): string {
  return `${String((instant / span) * 100)}%`;
}
