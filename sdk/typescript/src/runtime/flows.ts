/** A flow: a function that outlives a call. It runs in this process; the gateway keeps its journal, its clock and what wakes it. */

import { cancelRun, endRun, readRun, runsOf, startRun, writeStep, type AppDoor, type JournalStep, type KeptRun } from "../client/app-work.js";

import type { Agent } from "../agent/agent.js";
import { DeclarationRefused } from "../agent/tools.js";

type Ctor = new () => Agent;
type Data = Record<string, unknown>;

/** What a call a flow placed came to. `refused` names why nothing rang: a dial guard, or nobody holding the agent. */
export interface Called {
  answered: boolean;
  reason?: string;
  call?: string;
  refused?: string;
  message?: string;
}

/** What a call a flow places opens with. */
export interface Opening {
  state?: Data;
  metadata?: Data;
  /** The words the call opens with, over the agent's own greeting. */
  greeting?: string;
  /** What the call is for: the agent reads it for the whole call and, with no greeting, opens on it. */
  instruction?: string;
  /** Which of the agent's numbers the far end sees. */
  from?: string;
}

/** The steps of a flow. Each is written to the run's journal: on the next run of the function it answers what it came to. */
export interface Step {
  /** Sleep for a while: `"2h"`, `"30m"`, `"45s"`, `"1d"`. */
  sleep(howLong: string): Promise<void>;
  /** Sleep until a time, or until `before` it: `step.sleepUntil(visit.at, { before: "24h" })`. */
  sleepUntil(at: Date | string, options?: { before?: string }): Promise<void>;
  /** Have an agent call a number, and wait for how the call ended. */
  call(to: string, agent: Ctor, opening?: Opening): Promise<Called>;
  /** Wait for an event of the app whose data has what `match` names, for `within` at most; null when it gave up. */
  waitFor(event: string, options?: { match?: Data; within?: string }): Promise<Data | null>;
  /** Run something once: what it returned is kept, and read back instead of run again. */
  run<T>(effect: () => T | Promise<T>): Promise<T>;
  /** Send an event to the app. */
  emit(name: string, data?: Data): Promise<void>;
}

/** The body of a flow: what started it, and its steps. */
export type FlowBody = (input: Data, step: Step) => unknown;

/** A flow by its name, which is how the gateway knows its runs. */
export class Flow {
  readonly cancels: { event: string; when: (event: Data, input: Data) => boolean }[] = [];

  constructor(
    readonly name: string,
    readonly body: FlowBody,
  ) {}

  /** Cancel the runs still waiting when an event says so: `remind.cancelOn("visit.cancelled", (gone, visit) => gone.id === visit.id)`. */
  cancelOn(event: string, when: (event: Data, input: Data) => boolean): this {
    this.cancels.push({ event, when });
    return this;
  }
}

const A_NAME = /^[a-z0-9][a-z0-9-]*$/;
const A_WHILE = /^(\d+)(s|m|h|d)$/;
const SECONDS = { s: 1, m: 60, h: 3600, d: 86400 } as const;
// What a run still waiting is in: the ones an event may cancel.
const WAITING = ["ready", "sleeping", "waiting", "calling"];

/** A flow named once: `export const remindVisit = flow("remind-visit", async (visit, step) => { … })`. */
export function flow(name: string, body: FlowBody): Flow {
  if (typeof name !== "string" || !A_NAME.test(name)) throw new DeclarationRefused("a flow's name is lowercase letters, digits and dashes: its runs are kept by it");
  if (typeof body !== "function") throw new DeclarationRefused(`${name}: a flow is its name and a function of what started it and its steps`);
  return new Flow(name, body);
}

/** Whether something handed to `app.on` is a flow, and not a plain handler. */
export function isFlow(given: unknown): given is Flow {
  return given instanceof Flow;
}

/** Seconds in `"2h"`, `"30m"`, `"45s"`, `"1d"`. */
export function secondsOf(howLong: string): number {
  const found = A_WHILE.exec(typeof howLong === "string" ? howLong.trim() : "");
  if (found === null) throw new DeclarationRefused(`"${String(howLong)}" is no length of time: a number and s, m, h or d, like 2h`);
  return Number(found[1]) * SECONDS[found[2] as keyof typeof SECONDS];
}

// Thrown to leave the function where it stands: the step is written and the run waits at the gateway.
class Parked extends Error {}

/** Thrown when a step could not be written: the run is left as it was, and the gateway hands it out again. */
export class StepUnwritten extends Error {
  override readonly name = "StepUnwritten";
}

// A gateway that did not answer is no failure of the flow: the run is not ended over it.
async function kept<T>(writing: Promise<T>): Promise<T> {
  try {
    return await writing;
  } catch (failed) {
    throw new StepUnwritten(failed instanceof Error ? failed.message : String(failed));
  }
}

/** Thrown when the function asks for another step than its journal holds at that place: its code changed under the run. */
export class FlowChanged extends Error {
  override readonly name = "FlowChanged";
}

/** Start a run of the flow; the same key is the same run. */
export function started(door: AppDoor, of: Flow, key: string, input: Data): Promise<KeptRun> {
  return startRun(door, of.name, key, input);
}

/** Cancel the flow's waiting runs an event names. */
export async function cancelled(door: AppDoor, of: Flow, event: string, data: Data): Promise<number> {
  const asking = of.cancels.filter((one) => one.event === event);
  if (asking.length === 0) return 0;
  let stopped = 0;
  for (const status of WAITING) {
    for (const run of await runsOf(door, of.name, status)) {
      if (!asking.some((one) => one.when(data, run.input))) continue;
      await cancelRun(door, run.id);
      stopped++;
    }
  }
  return stopped;
}

/** Where a stretch of a run left it; a failed one says what its function threw. */
export type Advanced = { status: "parked" | "done" } | { status: "failed"; error: string };

/**
 * Run the flow's function against the run's journal: a step already written answers what it came
 * to, and the first one that is not is written and, when it waits, leaves the function there. The
 * run is ended when the function returns or throws, and left as it was when the gateway could not
 * be written to; `slugOf` names the agent a call step dials as.
 */
export async function advance(door: AppDoor, of: Flow, run: KeptRun, slugOf: (agent: Ctor) => string | undefined): Promise<Advanced> {
  const journal = new Map(run.steps.map((step) => [step.seq, step]));
  let seq = 0;
  const written = (kind: JournalStep["kind"]): JournalStep | undefined => {
    const before = journal.get(++seq);
    if (before !== undefined && before.kind !== kind) throw new FlowChanged(`${of.name}: step ${seq} was a ${before.kind} and is now a ${kind}: the flow's code changed under run ${run.id}`);
    return before;
  };
  // A step that waits: written, and the function left there unless the gateway answered it at once.
  const waited = async (kind: "sleep" | "wait" | "call", asked: Data): Promise<unknown> => {
    const before = written(kind);
    if (before?.over === true) return before.result;
    if (before !== undefined) throw new Parked();
    const after = await kept(writeStep(door, run.id, { seq, kind, asked }));
    if (after.status !== "ready") throw new Parked();
    return (await kept(readRun(door, run.id))).steps.find((step) => step.seq === seq)?.result;
  };
  const step: Step = {
    sleep: async (howLong) => void (await waited("sleep", { until: new Date(Date.now() + secondsOf(howLong) * 1000).toISOString() })),
    sleepUntil: async (at, options = {}) => {
      const until = new Date(at).getTime() - (options.before === undefined ? 0 : secondsOf(options.before) * 1000);
      if (Number.isNaN(until)) throw new DeclarationRefused(`${of.name}: sleepUntil takes a time, a Date or an ISO string`);
      await waited("sleep", { until: new Date(until).toISOString() });
    },
    call: async (to, agent, opening = {}) => {
      const slug = slugOf(agent);
      if (slug === undefined) throw new DeclarationRefused(`${of.name}: ${agent.name} is no agent this process serves`);
      return (await waited("call", { agent: slug, to, ...opening })) as Called;
    },
    waitFor: async (event, options = {}) => {
      const until = options.within === undefined ? {} : { until: new Date(Date.now() + secondsOf(options.within) * 1000).toISOString() };
      return ((await waited("wait", { event, ...(options.match === undefined ? {} : { match: options.match }), ...until })) ?? null) as Data | null;
    },
    run: async <T>(effect: () => T | Promise<T>): Promise<T> => {
      const before = written("run");
      if (before !== undefined) return before.result as T;
      const result = await effect();
      await kept(writeStep(door, run.id, { seq, kind: "run", result: result ?? null }));
      return result;
    },
    emit: async (name, data = {}) => {
      if (written("emit") === undefined) await kept(writeStep(door, run.id, { seq, kind: "emit", asked: { name, data } }));
    },
  };
  try {
    await of.body(run.input, step);
  } catch (thrown) {
    if (thrown instanceof Parked) return { status: "parked" };
    if (thrown instanceof StepUnwritten) throw thrown;
    const error = thrown instanceof Error ? `${thrown.name}: ${thrown.message}` : String(thrown);
    await endRun(door, run.id, "failed", error);
    return { status: "failed", error };
  }
  await endRun(door, run.id, "done");
  return { status: "done" };
}
