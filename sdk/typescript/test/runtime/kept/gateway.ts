// A gateway's flows endpoints in memory: the runs and events of one app, answered to `fetch` as the runtime answers them.

import type { JournalStep, KeptRun, OwedEvent } from "../../../src/client/app-work.js";

const WAITS: Record<string, string> = { sleep: "sleeping", wait: "waiting", call: "calling" };

/** The app's runs and events, and what was asked of the gateway, in order. */
export class KeptApp {
  readonly runs = new Map<string, KeptRun>();
  readonly keys = new Map<string, string>();
  readonly events: OwedEvent[] = [];
  readonly heard: number[] = [];
  readonly asked: string[] = [];
  /** A call step answered at once, as a dial a guard refused is. */
  refuses: unknown;
  /** What a call told to take another agent's stages is answered. */
  staged = 202;
  /** When set, every write of a step fails with it. */
  down: string | undefined;

  readonly door = { url: "https://gateway.test", apiKey: "pk_test", app: "brightside" };

  /** The step the run waits on comes to `result`, and the run is ready again. */
  wake(run: string, result: unknown): void {
    const kept = this.runs.get(run)!;
    const open = kept.steps.find((step) => !step.over)!;
    open.over = true;
    open.result = result;
    kept.status = "ready";
  }

  /** Keep an event for the app, as its own backend sends one. */
  send(name: string, data: Record<string, unknown>): number {
    const id = this.events.length + 1;
    this.events.push({ id, name, data });
    return id;
  }

  /** What `fetch` is replaced with. */
  readonly fetch = async (url: string | URL, init: RequestInit = {}): Promise<Response> => {
    const { pathname, searchParams } = new URL(String(url));
    if (pathname.endsWith("/stages")) {
      this.asked.push(`${init.method} ${pathname} ${String(init.body)}`);
      return new Response(JSON.stringify({ call: "CA_1" }), { status: this.staged });
    }
    const path = pathname.replace("/v1/apps/brightside", "");
    const body = typeof init.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {};
    this.asked.push(`${init.method} ${path}`);
    const answer = (status: number, value: unknown): Response => new Response(value === undefined ? null : JSON.stringify(value), { status });
    const parts = path.split("/").filter(Boolean);
    if (path === "/work") {
      const owed = this.events.filter((event) => !this.heard.includes(event.id));
      return answer(200, { events: owed, runs: [...this.runs.values()].filter((run) => run.status === "ready").map((run) => structuredClone(run)) });
    }
    if (parts[0] === "events" && parts[2] === "heard") {
      this.heard.push(Number(parts[1]));
      return answer(204, undefined);
    }
    if (path === "/runs" && init.method === "POST") {
      const key = `${String(body["flow"])}:${String(body["key"])}`;
      const before = this.keys.get(key);
      if (before !== undefined) return answer(201, this.runs.get(before));
      const run: KeptRun = { id: `run_${this.runs.size + 1}`, flow: String(body["flow"]), input: body["input"] as Record<string, unknown>, status: "ready", steps: [] };
      this.runs.set(run.id, run);
      this.keys.set(key, run.id);
      return answer(201, run);
    }
    if (path === "/runs") {
      const found = [...this.runs.values()].filter((run) => run.flow === searchParams.get("flow") && run.status === searchParams.get("status"));
      return answer(200, { runs: found.map((run) => ({ ...run, steps: [] })) });
    }
    const run = this.runs.get(parts[1] ?? "");
    if (run === undefined) return answer(404, { detail: "no such run" });
    if (parts[2] === undefined) return answer(200, structuredClone(run));
    if (parts[2] === "end") run.status = String(body["status"]);
    if (parts[2] === "cancel") run.status = "cancelled";
    if (parts[2] === "steps") {
      if (this.down !== undefined) return answer(503, { detail: this.down });
      const kind = body["kind"] as JournalStep["kind"];
      const step: JournalStep = { seq: Number(body["seq"]), kind, asked: (body["asked"] as Record<string, unknown>) ?? {}, over: false, result: null };
      if (kind === "run" || kind === "emit") Object.assign(step, { over: true, result: body["result"] ?? null });
      else if (kind === "call" && this.refuses !== undefined) Object.assign(step, { over: true, result: this.refuses });
      else run.status = WAITS[kind]!;
      if (kind === "emit") this.send(String(step.asked["name"]), step.asked["data"] as Record<string, unknown>);
      run.steps.push(step);
    }
    return answer(200, { ...run, steps: [] });
  };
}
