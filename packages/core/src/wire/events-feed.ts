/** What a feed says of a change no log holds: a run, a release, a worker, a tool, a judge, by ids alone. */

import { z } from "zod";

/** A hosted app did not build, start or stay up: the org's alert, posted to its webhook, on no agent's log. */
export const AppFailedSchema = z.strictObject({
  app: z.string(),
  host: z.string(),
  release: z.int().nullish(),
  why: z.string(),
});

/** A newborn org has had no call that went well: the operators' alert, said once, on no agent's log. */
export const OrgQuietSchema = z.strictObject({
  org: z.string(),
  name: z.string(),
  created_at: z.number(),
  calls: z.int(),
  failed: z.int(),
});

/** A hosted app's release changed where it stands: uploaded, live, failed or replaced. */
export const ReleaseChangedSchema = z.strictObject({
  app: z.string(),
  release: z.int(),
});

/** A run of goldens and cases opened a call, judged one, or finished. */
export const RunChangedSchema = z.strictObject({
  run: z.string(),
  agent: z.string(),
  finished: z.boolean(),
});

/** A worker of a fleet was first heard, cordoned, uncordoned, or stopped being heard. */
export const WorkerChangedSchema = z.strictObject({
  worker: z.string(),
  fleet: z.string(),
  up: z.boolean(),
  cordoned: z.boolean(),
});

/** A tool of a call answered; its name and seconds, never its arguments or its output. */
export const ToolRanSchema = z.strictObject({
  call: z.string(),
  agent: z.string(),
  name: z.string(),
  duration_s: z.number().nullable(),
});

/** A tool of a call failed or timed out; its name and seconds, never its error, arguments or output. */
export const ToolFailedSchema = z.strictObject({
  call: z.string(),
  agent: z.string(),
  name: z.string(),
  duration_s: z.number().nullable(),
});

/** A judge found a sealed call broken; its name, never its reason or its evidence. */
export const JudgeBrokeSchema = z.strictObject({
  call: z.string(),
  agent: z.string(),
  judge: z.string(),
});
