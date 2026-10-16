/** Metrics panel: median turn latencies as bars, then every metric block. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type CollectedMetrics } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import { blockShapes, measured, medians, readings, TALK_SHARE, type MetricsBlock } from "@pinecall/core/metrics";
import type { Shape } from "@pinecall/core/compact-json";
import { Bar, SectionLabel } from "../../ui";
import { Readings } from "./readings";

export function MetricsPanel({ metrics, entries }: { metrics: CollectedMetrics; entries: Entry[] }): ReactNode {
  const middle = medians(entries);
  // Seconds are drawn against the longest of them; the talk share is a share already.
  const longest = Math.max(...middle.filter((row) => row.name !== TALK_SHARE).map((row) => row.seconds), 0);
  const shareOf = (name: string, value: number): number => (name === TALK_SHARE ? value : longest === 0 ? 0 : value / longest);
  const shapes = blockShapes();
  return (
    <>
      <SectionLabel ruled>Metrics</SectionLabel>
      <div className="call-pane-body">
        {middle.length === 0 && <div className="call-sub">Nothing measured yet: the first turn fills this in.</div>}
        {middle.map((row) => (
          <div className="call-meter" key={row.name} title={row.name === TALK_SHARE ? "of the time anybody spoke" : `median over ${String(row.turns)} turns`}>
            <span className="call-meter-name">{row.name}</span>
            <Bar share={shareOf(row.name, row.seconds)} />
            <span className="call-meter-value">{measured(row.name, row.seconds)}</span>
          </div>
        ))}
        {Object.entries(metrics).map(([kind, blocks]) => (
          <Blocks key={kind} kind={kind} blocks={blocks} shape={shapes.get(kind)} />
        ))}
      </div>
    </>
  );
}

// Includes session-level blocks no turn owns (vad, eot, interruption, realtime, avatar).
function Blocks({ kind, blocks, shape }: { kind: string; blocks: MetricsBlock[]; shape: Shape | undefined }): ReactNode {
  if (blocks.length === 0) {
    return null;
  }
  return (
    <details className="call-blocks">
      <summary>
        metrics.{kind} · {blocks.length}
      </summary>
      {blocks.map((block, index) => (
        <Readings key={`${kind}-${String(index)}`} rows={readings(block, shape)} />
      ))}
    </details>
  );
}
