/** The loop a voice app's process keeps with the gateway: the events it is owed are heard, and its flows' runs go on. */

import { eventHeard, takeWork, type AppDoor } from "../client/app-work.js";
import { stagedAs } from "../client/staged.js";
import type { Entry } from "../wire/envelope.js";

import type { Agent } from "../agent/agent.js";

import type { VoiceApp } from "./app.js";
import { advance, cancelled, started } from "./flows.js";
import { PASSED } from "./handoff.js";

type Ctor = new () => Agent;

/** How long one ask for work waits at the gateway. */
const WAITS_S = 20;
/** How long the loop rests after a gateway that did not answer. */
const RESTS_MS = 5000;

/** What the loop needs: the app, the gateway, the slug each class is served as, and where a failure is said. */
export interface Working {
  app: VoiceApp;
  door: AppDoor;
  slugOf: (agent: Ctor) => string | undefined;
  report: (line: string) => void;
}

/**
 * What an entry of that name does to the app's flows: it starts a run of each flow `app.on` gave
 * it, kept by `key` so the same entry starts it once, and cancels the waiting runs that asked to be.
 */
export async function flowsHeard(working: Working, name: string, data: Record<string, unknown>, key: string): Promise<void> {
  const { app, door, report } = working;
  for (const flow of app.startedBy(name)) {
    await started(door, flow, key, data).catch((failed: Error) => report(`${flow.name} was not started by ${name}: ${failed.message}`));
  }
  for (const flow of app.flows()) {
    await cancelled(door, flow, name, data).catch((failed: Error) => report(`${flow.name} was not cancelled by ${name}: ${failed.message}`));
  }
}

/** The same for an entry of a call's log; one that is not kept starts nothing. */
export async function entryHeard(working: Working, entry: Entry): Promise<void> {
  if (entry.ephemeral) return;
  const { name, data } = working.app.named(entry);
  await flowsHeard(working, name, data, `${entry.call ?? entry.agent}:${entry.seq}`);
}

// A written call has no worker to tell (404), and one that ended has none either (409).
const NOTHING_TO_RESTAGE = [202, 404, 409];

/**
 * A call passed to a teammate takes that agent's model and voice: asked of the gateway when the
 * pass is heard on the call's log. The reply being said ends in the voice it began in.
 */
export async function passHeard(working: Working, entry: Entry): Promise<void> {
  const { name, data } = working.app.named(entry);
  if (name !== PASSED || entry.call === null || typeof data["to"] !== "string") return;
  const status = await stagedAs(working.door, entry.call, data["to"]).catch((failed: Error) => failed.message);
  if (!NOTHING_TO_RESTAGE.includes(status as number)) working.report(`${entry.call} keeps the voice it had after its pass to ${data["to"]}: the gateway answered ${status}`);
}

/** Take what the app is owed once: each event to its handlers and its flows, each run one stretch further. */
export async function workedOnce(working: Working, waitS: number, signal?: AbortSignal): Promise<void> {
  const { app, door, slugOf, report } = working;
  const owed = await takeWork(door, waitS, signal);
  for (const event of owed.events) {
    await app.heard({ type: event.name, call: null, agent: "", data: event.data }, (name, error) => report(`the handler of ${name} threw: ${error.message}`));
    await flowsHeard(working, event.name, event.data, `event:${event.id}`);
    await eventHeard(door, event.id);
  }
  const known = new Map(app.flows().map((flow) => [flow.name, flow]));
  await Promise.all(
    owed.runs.map(async (run) => {
      const flow = known.get(run.flow);
      // Another release of the app may know the flow: the run is left for it.
      if (flow === undefined) return report(`run ${run.id} is of the flow ${run.flow}, which this app does not have`);
      const ended = await advance(door, flow, run, slugOf).catch((failed: Error) => report(`${run.flow} ${run.id}: ${failed.message}`));
      if (ended?.status === "failed") report(`${run.flow} ${run.id} failed: ${ended.error}`);
    }),
  );
}

/** Keep taking work until stopped; returns what stops it. */
export function work(working: Working): () => void {
  const stopping = new AbortController();
  let said = false;
  void (async () => {
    while (!stopping.signal.aborted) {
      try {
        await workedOnce(working, WAITS_S, stopping.signal);
        said = false;
      } catch (failed) {
        if (stopping.signal.aborted) return;
        // One line per outage.
        if (!said) working.report(`flows: ${failed instanceof Error ? failed.message : String(failed)}`);
        said = true;
        await new Promise((resolve) => setTimeout(resolve, RESTS_MS).unref());
      }
    }
  })();
  return () => stopping.abort();
}
