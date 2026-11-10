/** The operator's doors for the fleet: every worker heard from, each environment's totals, which fleet serves which environment, and the cordon. */

import { z } from "zod";

import { drop, post, read, type Credentials } from "@pinecall/core/api";

const OPS = "/v1/ops";

// Mirrors the runtime's roster (docs/protocol/operator-api.md, "The fleet"). Loose on purpose: a field
// the gateway adds never breaks the page. The same worker name can run in both fleets: the pair names it.
const WorkerSchema = z.looseObject({
  fleet: z.string(),
  worker: z.string(),
  /** `<fleet>/<worker>.<its start>`, once LiveKit has registered it; absent while it is still loading. */
  agent_name: z.string().nullish(),
  active: z.number(),
  /** Null: the worker is gated on its machine's load, not on a count of calls. */
  max_jobs: z.number().nullish(),
  /** Calls over seats, full at 1; for a worker with no count, its share of the machine, full at 0.7. */
  load: z.number(),
  draining: z.boolean(),
  cordoned: z.boolean(),
  seen_at: z.number(),
  // The worker's last minute; a worker of an older release says none.
  ended: z.number().nullish(),
  failed: z.number().nullish(),
  errors: z.number().nullish(),
  turns: z.number().nullish(),
  first_audio_p95_s: z.number().nullish(),
  /** No gateway says it today; shown the day one does. */
  version: z.string().nullish(),
});
export type Worker = z.infer<typeof WorkerSchema>;

// One fleet summed over the workers heard from lately.
const TotalsSchema = z.looseObject({
  fleet: z.string(),
  workers: z.number(),
  active: z.number(),
  seats: z.number(),
  free: z.number(),
  accepting: z.number(),
  full: z.boolean(),
  /** Rooms with a caller no worker opened in the last ten minutes. */
  waiting: z.number().default(0),
});
export type FleetTotals = z.infer<typeof TotalsSchema>;

const FleetSchema = z.looseObject({
  /** The gateway's clock: `seen_at` is compared with it, never with the browser's. */
  now: z.number(),
  stale_after_s: z.number(),
  workers: z.array(WorkerSchema),
  // A gateway from before the totals says none: the page sums the workers itself.
  totals: z.array(TotalsSchema).default([]),
});
export type TheFleet = z.infer<typeof FleetSchema>;

const FleetsSchema = z.looseObject({ production: z.string(), sandbox: z.string() });
export type FleetNames = z.infer<typeof FleetsSchema>;

/** Every worker heard from in the last hour, both fleets, and each fleet's totals. */
export async function readFleet(credentials: Credentials): Promise<TheFleet> {
  return FleetSchema.parse(await read(credentials, `${OPS}/fleet`));
}

/** The name of the fleet each environment's calls are dispatched to. */
export async function readFleetNames(credentials: Credentials): Promise<FleetNames> {
  return FleetsSchema.parse(await read(credentials, `${OPS}/fleets`));
}

/** Cordon a worker, or lift its cordon: told on its next heartbeat, and no call it holds is ended. */
export async function cordon(credentials: Credentials, worker: Worker, wanted: boolean): Promise<void> {
  const path = `${OPS}/fleet/${encodeURIComponent(worker.worker)}/cordon?fleet=${encodeURIComponent(worker.fleet)}`;
  await (wanted ? post(credentials, path, {}) : drop(credentials, path));
}
