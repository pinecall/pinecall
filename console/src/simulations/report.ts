/** A comparison's benchmark as the file `pinecall benchmark` writes: `report.json`, the same shape and the same numbers, its calls' lines read and no recording beside it. */

import { callersOf, endedOf, nameOf, rowsOf, VERSION, type Bars, type Benchmark } from "@pinecall/agents/evals";
import { read, type Credentials } from "@pinecall/core/api";

import { benchmarkOf, readAllHeard } from "./benchmark";
import { readCallers, type Comparison } from "./door";

/** The report of the comparisons named, held to the bars given: every call's log read for its lines. */
export async function reportOf(credentials: Credentials, tables: readonly Comparison[], bars: Bars): Promise<Benchmark> {
  const first = tables[0] as Comparison;
  const ended = endedOf(tables);
  const [heard, written, gateway] = await Promise.all([
    readAllHeard(credentials, ended.filter((row) => row.ended_at !== null), true),
    readCallers(credentials, first.agent).catch(() => []),
    read(credentials, "/.well-known/pinecall").catch(() => null) as Promise<{ version?: string } | null>,
  ]);
  const made = benchmarkOf(tables, bars, heard);
  const ids = tables.map((table) => table.comparison);
  return {
    version: VERSION,
    made_at: new Date().toISOString(),
    agent: first.agent,
    gateway: { url: new URL(credentials.base, window.location.origin).origin, env: credentials.world ?? "sandbox", version: gateway?.version ?? null },
    comparisons: ids,
    conditions: [],
    spoken: tables.some((table) => table.voice),
    // The calls are placed already: what makes this report again, with each call's recording beside it, is the verb that reads them.
    command: `pinecall benchmark ${ids.join(" ")}`,
    bars,
    verdict: made.verdict,
    callers: callersOf(tables).map((name) => {
      const one = written.find((persona) => persona.name === name);
      return { name, about: one?.about ?? "", goal: one?.goal ?? "", expects: one?.expects ?? [], behavior: one?.behavior ?? null };
    }),
    setups: made.setups,
    refused: tables.flatMap((table) => table.refused.map((one) => ({ caller: one.persona, setup: nameOf(one.against), why: one.why }))),
    on_the_line: rowsOf(tables).length - ended.length,
    baseline: null,
    calls: made.calls,
  };
}

/** Hand the report to the browser as a file, named as the CLI names it. */
export function saveReport(report: Benchmark): void {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([`${JSON.stringify(report, null, 1)}\n`], { type: "application/json" }));
  link.download = "report.json";
  link.click();
  // Revoked once the browser has taken the download: revoked at once, some abort it.
  window.setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
}
