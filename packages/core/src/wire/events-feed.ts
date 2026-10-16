/** What a feed says of a change no log holds: a run, a release, a worker, each by its ids alone. */

import { z } from "zod";

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
