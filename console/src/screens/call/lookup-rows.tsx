/** Log rows for a turn's memory recall and knowledge retrieval. */

import { type DocsSources, type MemoryOps } from "@pinecall/core/wire/events";
import type { ReactNode } from "react";

import { factLines, memoryLine, sourceLines, sourcesLine } from "../../lib/lookups";
import { LogRow } from "./log-row";

/** Contact facts recalled from memory, with lookup latency. */
export function MemoryRow({ ops, seq }: { ops: MemoryOps; seq: number }): ReactNode {
  return <LookupRow kind="memory" said={memoryLine(ops)} lines={factLines(ops)} seq={seq} />;
}

/** Chunks retrieved from knowledge, with lookup latency. */
export function SourcesRow({ sources, seq }: { sources: DocsSources; seq: number }): ReactNode {
  return <LookupRow kind="sources" said={sourcesLine(sources)} lines={sourceLines(sources)} seq={seq} />;
}

function LookupRow({ kind, said, lines, seq }: { kind: string; said: string; lines: string[]; seq: number }): ReactNode {
  return (
    <LogRow seq={seq} kind={kind} tone="lookup" said={said}>
      <ul className="call-list">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </LogRow>
  );
}
