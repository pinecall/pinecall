/** A call read row by row, as the Log with every number or as the Transcript with only what was said and done; the words in progress last. */

import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { type Entry } from "@pinecall/core/wire/envelope";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { type State } from "@pinecall/core/wire/state";
import { type Broke, brokenAt, canBeCited } from "./broken";
import { heardSoFar } from "./heard";
import { ConfirmRow, EventRow, LogRow, MemoryRow, QuietRow, SourcesRow, StateRow, ToolRow, TurnRow } from "./log-rows";
import { rowsOf, type Row } from "./timeline-rows";

// Within this distance of the bottom, the list keeps following the call.
const NEAR_THE_END_PX = 80;

// The rows the Transcript shows: what was said and done.
const SPOKEN: readonly Row["kind"][] = ["turn", "tool", "confirm", "event", "supervisor", "line"];

function RowOf({ row, state, terse }: { row: Row; state: State; terse: boolean }): ReactNode {
  switch (row.kind) {
    case "turn":
      return <TurnRow turn={row.turn} seq={row.seq} metrics={state.metrics} terse={terse} />;
    case "tool":
      return <ToolRow run={row.run} seq={row.seq} />;
    case "state":
      return <StateRow changed={row.changed} cause={row.cause} seq={row.seq} />;
    case "confirm":
      return <ConfirmRow confirm={row.confirm} seq={row.seq} />;
    case "event":
      return <EventRow name={row.name} source={row.source} data={row.data} seq={row.seq} />;
    case "supervisor":
      return <LogRow seq={row.seq} kind="supervisor" tone="supervisor" said={row.mark.said} note={[row.mark.by]} />;
    case "line":
      return <LogRow seq={row.seq} kind="line" tone="handing" said={row.mark.said} note={[row.mark.note]} />;
    case "memory":
      return <MemoryRow ops={row.ops} seq={row.seq} />;
    case "sources":
      return <SourcesRow sources={row.sources} seq={row.seq} />;
    case "quiet":
      return <QuietRow entries={row.entries} />;
  }
}

function BrokenBy({ broke }: { broke: readonly Broke[] }): ReactNode {
  return (
    <div className="calls-broken-by">
      {broke.map((one) => (
        <p key={one.judge}>
          <b>{one.judge}</b> {one.reason}
        </p>
      ))}
    </div>
  );
}

// Words are keyed by position so each fades in only once; the newest is lit.
function Saying({ said, who }: { said: string | null; who: "caller" | "agent" }): ReactNode {
  if (said === null) return null;
  const spoken = said.split(/\s+/).filter((word) => word !== "");
  return (
    <div className="calls-saying">
      <LogRow
        seq={undefined}
        kind="turn"
        tone="turn"
        who={who}
        said={
          <>
            {spoken.map((word, at) => (
              <span key={at} className={at === spoken.length - 1 ? "calls-word calls-word-now" : "calls-word"}>
                {word}{" "}
              </span>
            ))}
            <span className="calls-caret" aria-hidden="true" />
          </>
        }
      />
    </div>
  );
}

export function Timeline({ entries, state, score, terse }: { entries: Entry[]; state: State; score: CallScore | null; terse: boolean }): ReactNode {
  const saying = state.live.agent;
  const heard = useMemo(() => heardSoFar(entries, state.live.user), [entries, state.live.user]);
  const rows = useMemo(() => rowsOf(entries, state), [entries, state]);
  const broken = useMemo(() => brokenAt(score, rows), [score, rows]);
  const list = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  useEffect(() => {
    const box = list.current;
    if (box !== null && following.current) box.scrollTop = box.scrollHeight;
  }, [entries, heard, saying]);

  return (
    <div
      className="calls-scroll"
      ref={list}
      onScroll={(event) => {
        const box = event.currentTarget;
        following.current = box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_THE_END_PX;
      }}
    >
      <div className="calls-log">
        {rows
          .filter((row) => !terse || SPOKEN.includes(row.kind))
          .map((row) => {
            const broke = broken.get(row.seq);
            return (
              <div key={`${row.kind}-${String(row.seq)}`} className={broke === undefined ? undefined : "calls-broken"} data-seq={canBeCited(row) ? row.seq : undefined}>
                <RowOf row={row} state={state} terse={terse} />
                {broke !== undefined && <BrokenBy broke={broke} />}
              </div>
            );
          })}
        <Saying said={heard} who="caller" />
        <Saying said={saying} who="agent" />
      </div>
    </div>
  );
}
