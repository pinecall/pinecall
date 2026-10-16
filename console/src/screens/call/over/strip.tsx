/** The latency of one call, median and max per measure — the terminal's numbers, on a card. */

import type { ReactNode } from "react";

import { measured, TALK_SHARE, type Median } from "@pinecall/core/metrics";
import { Card, CardHead } from "../../../ui";

// What a person calls each of livekit's five measures and the runtime's talk share. The measure itself
// keeps its name in the tooltip: nothing new is measured here, every value is the median or the max
// of the per-turn chips `pinecall-runtime sessions show <id>` prints, so the two can be held side by side.
export const SAID: Record<string, string> = {
  llm_node_ttft: "LLM first token",
  e2e_latency: "End to end",
  tts_node_ttfb: "Speech starts",
  transcription_delay: "Transcription",
  end_of_turn_delay: "End of turn",
  talk_share: "Agent talks",
};

// The two a caller feels first, then the rest in the order a turn happens.
const FIRST = ["llm_node_ttft", "e2e_latency"];

export function LatencyCard({ rows }: { rows: Median[] }): ReactNode {
  const ordered = [...rows.filter((row) => FIRST.includes(row.name)).sort((a, b) => FIRST.indexOf(a.name) - FIRST.indexOf(b.name)), ...rows.filter((row) => !FIRST.includes(row.name))];
  return (
    <Card>
      <CardHead title="Latency across this call" />
      {ordered.length === 0 ? (
        <p className="over-sentence over-latency-none">
          No turn in this session carried a metric — a chat session times nothing, and a voice call that dropped before its first answer has nothing to time.
        </p>
      ) : (
        <div className="over-latency">
          {ordered.map((row) => (
            <div key={row.name} title={row.name === TALK_SHARE ? `${row.name} · of the time anybody spoke` : `${row.name} · median over ${row.turns} ${row.turns === 1 ? "turn" : "turns"}`}>
              <div className="over-latency-label">{SAID[row.name] ?? row.name}</div>
              <div className="over-latency-value">{measured(row.name, row.seconds)}</div>
              {/* One share per call: it has no max. */}
              {row.name !== TALK_SHARE && <div className="over-latency-max">max {measured(row.name, row.max)}</div>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
