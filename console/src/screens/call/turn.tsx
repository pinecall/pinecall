/** Turn row: speaker, text, headline metrics, and the full metric blocks. */

import { type CollectedMetrics, type Turn } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import { blocksFor, headline } from "@pinecall/core/metrics";
import { LogRow } from "./log-row";
import { Readings } from "./readings";

// Short labels for the headline metrics; the expander keeps LiveKit's names.
const SHORT: Record<string, string> = {
  transcription_delay: "stt",
  end_of_turn_delay: "eot",
  llm_node_ttft: "ttft",
  tts_node_ttfb: "ttfb",
  e2e_latency: "e2e",
};

/** Blocks are those joined to the turn by speech_id; `terse` shows the text only. */
export function TurnRow({ turn, seq, metrics, terse = false }: { turn: Turn; seq: number; metrics: CollectedMetrics; terse?: boolean }): ReactNode {
  const blocks = blocksFor(metrics, turn.speech_id);
  const readings = headline(turn).map((reading) => `${SHORT[reading.field] ?? reading.field} ${reading.value}`);
  const interrupted = turn.role === "agent" && turn.interrupted ? ["interrupted"] : [];
  const language = turn.role === "user" && turn.language !== undefined && turn.language !== null ? [turn.language] : [];
  // Terse mode keeps only the interrupted flag.
  const note = terse ? interrupted : turn.role === "user" ? [...readings, turn.speech_id, ...language] : [...readings, ...interrupted];
  return (
    <LogRow seq={seq} kind="turn" tone="turn" who={turn.role === "agent" ? "agent" : "caller"} said={turn.text} note={note}>
      {terse || blocks.length === 0
        ? null
        : blocks.map((block, index) => (
            <section key={`${block.kind}-${String(index)}`}>
              <h4 className="call-block-name">metrics.{block.kind}</h4>
              <Readings rows={block.readings} />
            </section>
          ))}
    </LogRow>
  );
}
