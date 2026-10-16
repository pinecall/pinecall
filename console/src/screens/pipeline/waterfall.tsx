/** Turn latency chart: one bar per stage, scaled to the slowest, with its median. */

import type { ReactNode } from "react";

import { MEASURES } from "@pinecall/core/metrics";
import type { Measured } from "./door";

// Medians in seconds. Unmeasured stages show a dash, not a zero-width bar (which reads as instant).
// Stages overlap in time, so bars are independent, not slices of e2e.
const ROWS: Record<(typeof MEASURES)[number], { label: string; note: string; color: string }> = {
  transcription_delay: { label: "Transcription", note: "from the end of speech to the ear's final transcript", color: "var(--accent-3)" },
  end_of_turn_delay: { label: "End of turn", note: "silence the turn detector waits through before it believes the caller stopped", color: "var(--accent-3)" },
  llm_node_ttft: { label: "LLM first token", note: "to the model's first token", color: "var(--accent)" },
  tts_node_ttfb: { label: "Speech starts", note: "to the voice's first audio byte", color: "var(--accent-2)" },
  e2e_latency: { label: "End to end", note: "what the caller actually waits: their last word to the agent's first audio", color: "var(--accent-hover)" },
};

export function Waterfall({ medians, calls, agent }: { medians: Measured[]; calls: number; agent: string }): ReactNode {
  const measured = new Map(medians.map((row) => [row.name, row]));
  const slowest = Math.max(0, ...medians.map((row) => row.seconds));
  const turns = Math.max(0, ...medians.map((row) => row.turns));

  return (
    <div className="ui-card">
      <div className="ui-card-head">
        <span className="ui-card-title">Anatomy of a turn</span>
        {slowest > 0 && (
          <span className="ui-card-meta">
            medians over the last {calls} call{calls === 1 ? "" : "s"} · {turns} turns
          </span>
        )}
      </div>
      <div className="pipe-anatomy">
        {MEASURES.map((name, index) => {
          const row = ROWS[name];
          const took = measured.get(name)?.seconds ?? null;
          return (
            <div key={name} className={index === MEASURES.length - 1 ? "pipe-turn-row pipe-turn-row-last" : "pipe-turn-row"} title={row.note}>
              <span className="pipe-turn-label">{row.label}</span>
              <span className="pipe-track">
                {took !== null && slowest > 0 && <span className="pipe-bar" style={{ width: `${Math.max((took / slowest) * 100, 0.8)}%`, background: row.color }} />}
              </span>
              <span className={took === null ? "pipe-ms pipe-ms-none" : "pipe-ms"}>{took === null ? "—" : `${Math.round(took * 1000)} ms`}</span>
            </div>
          );
        })}
      </div>
      {slowest === 0 && <div className="ui-card-foot">{nothingMeasured(calls, agent)}</div>}
    </div>
  );
}

function nothingMeasured(calls: number, agent: string): string {
  if (calls === 0) return `No call stored for ${agent} yet — place one and the bars fill.`;
  return `${calls} stored call${calls === 1 ? "" : "s"} for ${agent}, and not one turn carries a latency — a text session measures none.`;
}
