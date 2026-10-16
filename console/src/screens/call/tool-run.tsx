/** Tool call row: name, arguments, and the expandable result. */

import { type ToolRun } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import { seconds, type Reading } from "@pinecall/core/metrics";
import { LogRow } from "./log-row";
import { Readings } from "./readings";

/** Shows running until the result arrives, then the result or error. */
export function ToolRow({ run, seq }: { run: ToolRun; seq: number }): ReactNode {
  return (
    <LogRow
      seq={seq}
      kind="tool"
      tone="tool"
      said={`${run.name}(${argumentsOf(run)})`}
      note={[<span className={run.status === "failed" ? "call-failed" : ""}>{outcomeOf(run)}</span>]}
    >
      <Readings rows={toolReadings(run)} />
    </LogRow>
  );
}

/** A tool's arguments, and once it answered its output or error and how long it took. */
export function toolReadings(run: ToolRun): Reading[] {
  return [
    { field: "arguments", value: JSON.stringify(run.arguments, null, 2), unit: null },
    ...(there(run.output) ? [{ field: "output", value: JSON.stringify(run.output, null, 2), unit: null }] : []),
    ...(there(run.error) ? [{ field: "error", value: run.error, unit: null }] : []),
    ...(there(run.duration_s) ? [{ field: "duration_s", value: seconds(run.duration_s), unit: null }] : []),
  ];
}

// Optional fields may be absent or null (pydantic `T | None = None`; zod `.nullish()`).
function there<T>(value: T): value is NonNullable<T> {
  return value !== undefined && value !== null;
}

// Short one-line summary; full arguments are in the expander.
function argumentsOf(run: ToolRun): string {
  return Object.entries(run.arguments)
    .map(([name, value]) => `${name}=${short(value)}`)
    .join(", ");
}

function outcomeOf(run: ToolRun): string {
  if (run.status === "running") {
    return "…";
  }
  return run.error ?? run.summary ?? short(run.output);
}

function short(value: unknown): string {
  const said = typeof value === "string" ? value : JSON.stringify(value);
  return said === undefined ? "" : said.slice(0, 60);
}
