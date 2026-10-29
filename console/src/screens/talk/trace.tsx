/** The call live, taken apart: what the caller is waiting on this instant, every reply as a trace, the models, the counts. */
//
// Everything is the call's own log (exchanges.ts): no number here is estimated. The one clock the pane
// keeps is the stopwatch while the caller waits — from their last word, as the log said it, to the
// agent's first sound — and it gives way to the wire's own measurement the moment that lands.

import { type Entry } from "@pinecall/core/wire/envelope";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { feltOf, rank, traceOf, type Bar, type Exchange, type Lane, type Trace as Traced } from "./exchanges";
import "./trace.css";

interface Props {
  entries: readonly Entry[];
  /** `live` runs on the page's clock, `still` not at all. */
  clock: "live" | "still";
}

const LANES: { lane: Lane; name: string }[] = [
  { lane: "hears", name: "hears" },
  { lane: "thinks", name: "thinks" },
  { lane: "tools", name: "tools" },
  { lane: "speaks", name: "speaks" },
];

const ms = (seconds: number): number => Math.round(seconds * 1000);
const secondsText = (seconds: number): string => (seconds < 10 ? seconds.toFixed(2) : seconds.toFixed(1));

/** Epoch seconds as the log's clock reads them now: the page's clock less the least delay seen. */
function useLogClock(entries: readonly Entry[], clock: Props["clock"]): number {
  const skew = useRef<number | null>(null);
  const first = entries[0]?.seq;
  useEffect(() => {
    skew.current = null;
  }, [first]);
  const last = entries.at(-1);
  if (clock === "live" && last) {
    const seen = Date.now() / 1000 - last.ts;
    skew.current = skew.current === null ? seen : Math.min(skew.current, seen);
  }
  const running = clock === "live";
  const [, tick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const slow = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let timer = 0;
    const step = (): void => {
      tick((n) => n + 1);
      if (slow) timer = window.setTimeout(step, 250);
      else frame = window.requestAnimationFrame(step);
    };
    step();
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [running]);
  if (clock === "live") return Date.now() / 1000 - (skew.current ?? 0);
  return last?.ts ?? 0;
}

export function Trace({ entries, clock }: Props): ReactNode {
  const live = clock === "live";
  const trace = useMemo(() => traceOf(entries, live), [entries, live]);
  const now = useLogClock(entries, clock);
  const [picked, setPicked] = useState<string | null>(null);
  const latest = trace.exchanges.at(-1);
  const shown = trace.exchanges.find((ex) => ex.id === picked) ?? latest;

  if (!latest && trace.waitingSince === null && trace.models.thinks === null) {
    return <p className="tr-quiet">The first reply is taken apart here as it happens: what the caller waits on, and for how long.</p>;
  }

  return (
    <section className="tr ui-fixed" aria-label="The call, live">
      <Now trace={trace} now={now} live={live} />
      <Pipeline trace={trace} />
      {shown && <Waterfall exchange={shown} now={now} latest={shown === latest} />}
      <Replies trace={trace} picked={shown?.id ?? null} pick={(id) => setPicked(id === latest?.id ? null : id)} />
      <Counts trace={trace} />
    </section>
  );
}

/** The number the caller feels: counting while they wait, the measured one once the agent is heard. */
//
// The count starts once the caller's turn has landed, from the moment they stopped as that turn
// says it: a pause in the middle of a sentence is not a wait, so it never resets the number. The
// last measured reply stays drawn under it the whole time, so nothing on the pane jumps.
function Now({ trace, now, live }: { trace: Traced; now: number; live: boolean }): ReactNode {
  const latest = trace.exchanges.at(-1);
  const waitingFrom = latest && !latest.done && latest.firstSound === null ? latest.zero : null;
  const felt = feltOf(trace);
  const sorted = [...felt].sort((a, b) => a - b);
  const waiting = live && waitingFrom !== null ? Math.max(0, now - waitingFrom) : null;
  const measured = [...trace.exchanges].reverse().find((ex) => ex.e2e !== null);
  const big = waiting ?? measured?.e2e ?? null;

  return (
    <div className="tr-now">
      <div className="tr-now-head">
        <span className="tr-eyebrow">{waiting !== null ? "caller stopped · waiting" : "caller stopped → it answered"}</span>
        <Doing now={trace.now} />
      </div>
      <div className={"tr-big" + (waiting !== null ? " is-counting" : "")}>
        {big === null ? (
          <span className="tr-dim">—</span>
        ) : (
          <>
            {secondsText(big)}
            <small>s</small>
          </>
        )}
      </div>
      {measured?.stages && <Breakdown exchange={measured} last={waiting !== null} />}
      {sorted.length > 1 && (
        <div className="tr-pcts">
          p50 <b>{rank(sorted, 0.5)}</b> · p95 <b>{rank(sorted, 0.95)}</b> · best <b>{sorted[0]}</b> ms · {sorted.length} replies
        </div>
      )}
    </div>
  );
}

/** The lit word for what is happening this instant. */
function Doing({ now }: { now: Traced["now"] }): ReactNode {
  if (now === null) return null;
  const words: Record<NonNullable<Traced["now"]>, string> = {
    you: "caller speaking",
    hears: "hearing them out",
    thinks: "thinking",
    tools: "running a tool",
    speaks: "speaking",
  };
  return (
    <span className={"tr-state is-" + now}>
      <i />
      {words[now]}
    </span>
  );
}

/** One reply's wait as one bar: each part as wide as it took, the rest named for what it is. */
function Breakdown({ exchange, last }: { exchange: Exchange; last: boolean }): ReactNode {
  const s = exchange.stages;
  const total = exchange.e2e;
  if (!s || !total) return null;
  const parts = [
    { lane: "hears", name: "heard them out", seconds: s.hears },
    { lane: "thinks", name: "first token", seconds: s.thinks ?? 0 },
    { lane: "speaks", name: "first audio", seconds: s.speaks ?? 0 },
    { lane: "other", name: "network", seconds: s.other ?? 0 },
  ].filter((part) => part.seconds > 0);
  const sum = parts.reduce((acc, part) => acc + part.seconds, 0) || total;
  return (
    <div className={"tr-break" + (last ? " is-last" : "")}>
      <div className="tr-break-bar">
        {parts.map((part) => (
          <span key={part.lane} className={"is-" + part.lane} style={{ flexGrow: part.seconds / sum }} />
        ))}
      </div>
      <div className="tr-break-keys">
        {parts.map((part) => (
          <span key={part.lane} className={"is-" + part.lane}>
            <i />
            {part.name} <b>{ms(part.seconds)}</b>
          </span>
        ))}
        {last && <span className="tr-break-was">the last reply</span>}
      </div>
    </div>
  );
}

/** The three models of the pipeline, the one at work lit. */
function Pipeline({ trace }: { trace: Traced }): ReactNode {
  const stages: { lane: Lane; name: string; model: string | null }[] = [
    { lane: "hears", name: "hears", model: trace.models.hears },
    { lane: "thinks", name: "thinks", model: trace.models.thinks },
    { lane: "speaks", name: "speaks", model: trace.models.speaks },
  ];
  if (stages.every((stage) => stage.model === null)) return null;
  return (
    <ol className="tr-pipe">
      {stages.map((stage) => (
        <li key={stage.lane} className={"is-" + stage.lane + (trace.now === stage.lane || (trace.now === "you" && stage.lane === "hears") ? " is-on" : "")}>
          <span className="tr-pipe-name">{stage.name}</span>
          <span className="tr-pipe-model" title={stage.model ?? undefined}>
            {stage.model ?? "—"}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** A tick every so many seconds, so a few fit the axis. */
function stepOf(span: number): number {
  for (const step of [0.25, 0.5, 1, 2, 5, 10, 20, 30, 60]) if (span / step <= 6) return step;
  return 120;
}

/** One exchange as a trace: every bar on its lane, from the caller's last word, growing while it happens. */
function Waterfall({ exchange, now, latest }: { exchange: Exchange; now: number; latest: boolean }): ReactNode {
  const open = latest && !exchange.done;
  const at = now - exchange.zero;
  const ends = exchange.bars.map((bar) => bar.to ?? (open ? at : bar.from));
  const span = Math.max(2, ...ends, open ? at : 0) * 1.04;
  const step = stepOf(span);
  const ticks = Array.from({ length: Math.floor(span / step) + 1 }, (_, i) => i * step);
  const x = (seconds: number): string => `${Math.max(0, Math.min(100, (seconds / span) * 100))}%`;
  const lanes = LANES.filter(({ lane }) => exchange.bars.some((bar) => bar.lane === lane));

  return (
    <div className="tr-fall">
      <div className="tr-fall-head">
        <span className="tr-eyebrow">{open ? "this reply, as it happens" : "the reply to"}</span>
        <span className="tr-said">“{exchange.said}”</span>
      </div>
      <div className="tr-grid">
        {lanes.map(({ lane, name }) => (
          <div key={lane} className={"tr-lane is-" + lane}>
            <span className="tr-lane-name">{name}</span>
            <div className="tr-track">
              {exchange.bars
                .filter((bar) => bar.lane === lane)
                .map((bar, i) => (
                  <Span key={i} bar={bar} at={at} open={open} x={x} />
                ))}
            </div>
          </div>
        ))}
        <div className="tr-lane tr-axis">
          <span />
          <div className="tr-track">
            {ticks.map((tick) => (
              <span key={tick} className="tr-tick" style={{ left: x(tick) }}>
                {tick === 0 ? "0" : `${tick}s`}
              </span>
            ))}
          </div>
        </div>
        {/* Over every lane: the moment the caller first heard it, and where the reply is now. */}
        <div className="tr-over" aria-hidden="true">
          {exchange.firstSound !== null && (
            <span className="tr-mark" style={{ left: x(exchange.firstSound) }}>
              <em>heard {secondsText(exchange.firstSound)}s</em>
            </span>
          )}
          {open && <span className="tr-cursor" style={{ left: x(at) }} />}
        </div>
      </div>
    </div>
  );
}

function Span({ bar, at, open, x }: { bar: Bar; at: number; open: boolean; x: (s: number) => string }): ReactNode {
  const to = bar.to ?? (open ? at : bar.from);
  const width = `calc(${x(to)} - ${x(bar.from)})`;
  const took = Math.max(0, to - bar.from);
  const title = `${bar.label} · ${ms(took)} ms${bar.to === null ? " so far" : ""}`;
  return (
    <span className={"tr-bar" + (bar.to === null ? " is-open" : "") + (bar.failed ? " is-failed" : "")} style={{ left: x(bar.from), width }} title={title}>
      {bar.first !== undefined && <span className="tr-first" style={{ width: `${((bar.first - bar.from) / Math.max(took, 0.001)) * 100}%` }} />}
      <span className="tr-bar-label">{bar.lane === "tools" ? bar.label : ms(took)}</span>
    </span>
  );
}

/** Every reply's wait, one column each, its parts stacked; a column picks the trace above. */
function Replies({ trace, picked, pick }: { trace: Traced; picked: string | null; pick: (id: string) => void }): ReactNode {
  const measured = trace.exchanges.filter((ex) => ex.e2e !== null);
  if (measured.length < 2) return null;
  const top = Math.max(...measured.map((ex) => ex.e2e ?? 0));
  return (
    <div className="tr-replies">
      <span className="tr-eyebrow">every reply · tap one</span>
      <div className="tr-cols">
        {measured.map((ex, i) => {
          const s = ex.stages;
          const total = ex.e2e ?? 0;
          const part = (seconds: number | null | undefined): string => `${((seconds ?? 0) / top) * 100}%`;
          return (
            <button key={ex.id} type="button" className={"tr-col" + (ex.id === picked ? " is-picked" : "")} onClick={() => pick(ex.id)} title={`reply ${i + 1} · ${ms(total)} ms`}>
              <span className="tr-col-stack" style={{ height: part(total) }}>
                <span className="is-other" style={{ flexGrow: s?.other ?? 0 }} />
                <span className="is-speaks" style={{ flexGrow: s?.speaks ?? 0 }} />
                <span className="is-thinks" style={{ flexGrow: s?.thinks ?? 0 }} />
                <span className="is-hears" style={{ flexGrow: s?.hears ?? (s ? 0 : 1) }} />
              </span>
              <span className="tr-col-ms">{ms(total)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** What the models did over the call, as counts. */
function Counts({ trace }: { trace: Traced }): ReactNode {
  const c = trace.counts;
  const k = (n: number): string => (n >= 10000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString("en"));
  const facts = [
    c.tokensIn > 0 && { name: "tokens in", value: k(c.tokensIn), aside: c.tokensCached > 0 ? `${Math.round((c.tokensCached / c.tokensIn) * 100)}% cached` : null },
    c.tokensOut > 0 && { name: "tokens out", value: k(c.tokensOut), aside: c.tokensPerSecond ? `${Math.round(c.tokensPerSecond)}/s` : null },
    c.voiced > 0 && { name: "voice made", value: `${c.voiced.toFixed(1)}s`, aside: `${k(c.characters)} chars` },
    c.tools > 0 && { name: "tools", value: String(c.tools), aside: c.toolsFailed ? `${c.toolsFailed} failed` : null },
    c.cut > 0 && { name: "cut short", value: String(c.cut), aside: null },
  ].filter((fact): fact is { name: string; value: string; aside: string | null } => Boolean(fact));
  if (facts.length === 0) return null;
  return (
    <dl className="tr-counts">
      {facts.map((fact) => (
        <div key={fact.name}>
          <dt>{fact.name}</dt>
          <dd>
            {fact.value}
            {fact.aside && <small>{fact.aside}</small>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
