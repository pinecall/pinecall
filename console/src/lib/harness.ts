/** The harness's numbers across the org: callers switched on, simulations run, goldens held in each agent's newest run, cases waiting, monitors fired. */

import { useEffect, useState } from "react";
import { z } from "zod";

import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { EvalCaseListSchema, MonitorListSchema, PersonaListSchema, PersonaRunListSchema } from "@pinecall/core/wire/rest-evals";

const RunsSchema = z.object({
  runs: z.array(
    z.looseObject({
      agent: z.string(),
      started_at: z.number(),
      matrix: z.looseObject({ runs: z.array(z.looseObject({ golden: z.string(), scores: z.array(z.looseObject({ passed: z.boolean() })) })) }).nullable(),
    }),
  ),
});

type Run = z.infer<typeof RunsSchema>["runs"][number];

export interface Harness {
  personas: number | null;
  simulations: number | null;
  goldens: { passing: number; failing: number; lastRun: number | null } | null;
  cases: number | null;
  monitors: { watching: number; fired: number } | null;
}

const NOTHING_READ: Harness = { personas: null, simulations: null, goldens: null, cases: null, monitors: null };

/** Goldens held in each agent's newest run that has a result: one fails when any of its cells did. */
function goldensIn(runs: readonly Run[]): NonNullable<Harness["goldens"]> {
  const newest = new Map<string, Run>();
  for (const run of runs) if (run.matrix !== null && !newest.has(run.agent)) newest.set(run.agent, run);
  let passing = 0;
  let failing = 0;
  for (const run of newest.values()) {
    const held = new Map<string, boolean>();
    for (const cell of run.matrix?.runs ?? []) held.set(cell.golden, (held.get(cell.golden) ?? true) && cell.scores.every((score) => score.passed));
    for (const one of held.values()) {
      if (one) passing += 1;
      else failing += 1;
    }
  }
  return { passing, failing, lastRun: runs[0]?.started_at ?? null };
}

/** Each station's number, read once per agent list; a door this key may not read stays null. */
export function useHarness(agents: readonly string[]): Harness {
  const credentials = useCredentials();
  const [harness, setHarness] = useState<Harness>(NOTHING_READ);
  const who = agents.join("\n");

  useEffect(() => {
    let gone = false;
    const land = (part: Partial<Harness>): void => {
      if (!gone) setHarness((was) => ({ ...was, ...part }));
    };
    const ignore = (): void => undefined;
    read(credentials, "/v1/personas").then((said) => land({ personas: PersonaListSchema.parse(said).personas.filter((one) => one.on).length }), ignore);
    read(credentials, "/v1/evals/runs", { limit: 200 }).then((said) => land({ goldens: goldensIn(RunsSchema.parse(said).runs) }), ignore);
    read(credentials, "/v1/evals/cases").then((said) => land({ cases: EvalCaseListSchema.parse(said).pending }), ignore);
    read(credentials, "/v1/monitors").then((said) => {
      const { monitors } = MonitorListSchema.parse(said);
      land({ monitors: { watching: monitors.length, fired: monitors.filter((one) => one.fired_on !== null).length } });
    }, ignore);
    const slugs = who === "" ? [] : who.split("\n");
    if (slugs.length === 0) land({ simulations: 0 });
    else read(credentials, "/v1/simulations", { agent: slugs }).then((said) => land({ simulations: PersonaRunListSchema.parse(said).total }), ignore);
    return () => {
      gone = true;
    };
  }, [credentials, who]);

  return harness;
}
