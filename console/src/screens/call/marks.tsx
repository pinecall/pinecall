/** Non-turn log rows: state changes, confirmations, external facts, supervisor actions, folded runs. */

import { type EventSource } from "@pinecall/core/wire/defs";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type StateCause } from "@pinecall/core/wire/events";
import { type Confirm } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import type { LineMark } from "../../lib/line-mark";
import type { SupervisorMark } from "../../lib/supervisor-mark";
import { LogRow } from "./log-row";
import { Readings } from "./readings";

/** A state change and its cause (tool result or external fact). */
export function StateRow({ changed, cause, seq }: { changed: string[]; cause: StateCause | null; seq: number }): ReactNode {
  return <LogRow seq={seq} kind="state" tone="state" said={`${changed.join(", ")} ← ${causeOf(cause)}`} />;
}

/** A supervisor action, with the token that identifies them. */
export function SupervisorRow({ mark, seq }: { mark: SupervisorMark; seq: number }): ReactNode {
  return <LogRow seq={seq} kind="supervisor" tone="supervisor" said={mark.said} note={[mark.by]} />;
}

/** Line events: transferred, held, or awaiting a human. */
export function LineRow({ mark, seq }: { mark: LineMark; seq: number }): ReactNode {
  return <LogRow seq={seq} kind="line" tone="handing" said={mark.said} note={[mark.note]} />;
}

/** A confirmation request, pending until granted or declined. */
export function ConfirmRow({ confirm, seq }: { confirm: Confirm; seq: number }): ReactNode {
  const rows = [
    { field: "tool", value: confirm.tool, unit: null },
    { field: "audience", value: confirm.audience, unit: null },
    ...(confirm.said == null ? [] : [{ field: "said", value: confirm.said, unit: null }]),
    ...(confirm.reason == null ? [] : [{ field: "reason", value: confirm.reason, unit: null }]),
  ];
  return (
    <LogRow seq={seq} kind="confirm" tone="confirm" said={confirm.phrase} note={[confirm.status]}>
      <Readings rows={rows} />
    </LogRow>
  );
}

/** An external fact delivered to the agent, with its source. */
export function EventRow({
  name,
  source,
  data,
  seq,
}: {
  name: string;
  source: EventSource;
  data: Record<string, unknown>;
  seq: number;
}): ReactNode {
  return (
    <LogRow seq={seq} kind="event" tone="event" said={name} note={[source]}>
      <pre className="call-data">{JSON.stringify(data, null, 2)}</pre>
    </LogRow>
  );
}

/** A run of non-conversation entries (metrics, session state, prompts, participants) folded into one row. */
export function QuietRow({ entries }: { entries: Entry[] }): ReactNode {
  return (
    <LogRow seq={entries[0]?.seq} kind="quiet" tone="quiet" said={entries.length === 1 ? "1 entry" : `${entries.length} entries`}>
      <ul className="call-list">
        {entries.map((entry) => (
          <li key={`${String(entry.seq)}-${entry.type}`}>
            {entry.seq} {entry.type}
          </li>
        ))}
      </ul>
    </LogRow>
  );
}

function causeOf(cause: StateCause | null): string {
  if (cause === null) {
    return "the app";
  }
  return cause.kind === "tool" ? cause.tool : `${cause.name} (seq ${String(cause.seq)})`;
}
