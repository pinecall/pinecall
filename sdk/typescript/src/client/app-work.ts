// A voice app's side of its flows: the events and the runs the gateway keeps for it, read and written over HTTP.

import { detailOf } from "./answered.js";
import { PinecallError } from "./frames.js";
import { signed, type World } from "./signed.js";

/** The gateway, the key and the app the work is asked for. */
export interface AppDoor {
  url: string;
  apiKey: string;
  env?: World | undefined;
  app: string;
}

/** An event the app is owed. */
export interface OwedEvent {
  id: number;
  name: string;
  data: Record<string, unknown>;
}

/** One step of a run's journal; `result` is what it came to once `over`. */
export interface JournalStep {
  seq: number;
  kind: "sleep" | "call" | "wait" | "run" | "emit";
  asked: Record<string, unknown>;
  over: boolean;
  result: unknown;
}

/** A run as the gateway keeps it. */
export interface KeptRun {
  id: string;
  flow: string;
  input: Record<string, unknown>;
  status: string;
  steps: JournalStep[];
}

/** What the app's process is owed now. */
export interface Work {
  events: OwedEvent[];
  runs: KeptRun[];
}

async function asked<T>(door: AppDoor, method: "GET" | "POST", path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const answered = await fetch(`${door.url.replace(/\/+$/, "")}/v1/apps/${encodeURIComponent(door.app)}${path}`, {
    method,
    headers: { ...signed(door.apiKey, door.env), "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    ...(signal === undefined ? {} : { signal }),
  });
  const text = await answered.text();
  if (!answered.ok) throw new PinecallError(`${door.app}${path}: the gateway answered ${answered.status}: ${detailOf(text)}`);
  return (text === "" ? undefined : JSON.parse(text)) as T;
}

/** What the app is owed, waited for up to `waitS` seconds: the gateway holds it for this process meanwhile. */
export const takeWork = (door: AppDoor, waitS: number, signal?: AbortSignal): Promise<Work> => asked(door, "POST", "/work", { wait_s: waitS }, signal);

/** Send an event to the app: kept until its process hears it. */
export const sendEvent = (door: AppDoor, name: string, data: Record<string, unknown>): Promise<{ id: number }> => asked(door, "POST", "/events", { name, data });

/** The event was handled. */
export const eventHeard = (door: AppDoor, id: number): Promise<void> => asked(door, "POST", `/events/${id}/heard`);

/** Start a flow with an input; the same key is the same run. */
export const startRun = (door: AppDoor, flow: string, key: string, input: Record<string, unknown>): Promise<KeptRun> => asked(door, "POST", "/runs", { flow, key, input });

/** Write the run's next step, and read the run as it stands after it. */
export const writeStep = (door: AppDoor, run: string, step: { seq: number; kind: JournalStep["kind"]; asked?: Record<string, unknown>; result?: unknown }): Promise<KeptRun> =>
  asked(door, "POST", `/runs/${encodeURIComponent(run)}/steps`, step);

/** One run with its journal. */
export const readRun = (door: AppDoor, run: string): Promise<KeptRun> => asked(door, "GET", `/runs/${encodeURIComponent(run)}`);

/** The app's runs of one flow in one status, newest first. */
export const runsOf = async (door: AppDoor, flow: string, status: string): Promise<KeptRun[]> =>
  (await asked<{ runs: KeptRun[] }>(door, "GET", `/runs?flow=${encodeURIComponent(flow)}&status=${encodeURIComponent(status)}`)).runs;

/** The flow returned or threw. */
export const endRun = (door: AppDoor, run: string, status: "done" | "failed", error?: string): Promise<KeptRun> => asked(door, "POST", `/runs/${encodeURIComponent(run)}/end`, { status, ...(error === undefined ? {} : { error }) });

/** Stop a run where it stands. */
export const cancelRun = (door: AppDoor, run: string): Promise<KeptRun> => asked(door, "POST", `/runs/${encodeURIComponent(run)}/cancel`);
