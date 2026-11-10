/** Fleet, the operator's page: whether calls are being answered, what needs a look first, and each environment's workers with the calls they hold and the cordon. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { ConfirmButton } from "../apps/confirm";
import { ago, count } from "../lib/format";
import { useOrg } from "../lib/org";
import { Copy, useMove } from "../numbers/parts";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { cordon, readFleet, readFleetNames, type FleetNames, type FleetTotals, type TheFleet, type Worker } from "./fleet-door";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../apps/apps.css";
import "../numbers/numbers.css";
import "../test/test.css";
import "./fleet.css";

// A worker changing is said on the box's feed; the clock only keeps "heard from" and a silent worker true.
const A_WORKER_CHANGED = ["worker.changed"] as const;
const REREAD_MS = 15_000;
// The roster's own lines (runtime fleet/service/roster.py): where a worker is full, and where its last minute is bad.
const FULL_BY_LOAD = 0.7;
const ENDED_TO_JUDGE = 4;
const FAILED_SHARE = 0.5;
const TURNS_TO_JUDGE = 20;
const SLOW_FIRST_AUDIO_S = 5;

type State = "struggling" | "gone" | "cordoned" | "draining" | "full" | "taking";
type Mood = "held" | "broke" | "none" | "waiting";

const STANDING: Readonly<Record<State, { mood: Mood; said: string; rank: number }>> = {
  struggling: { mood: "broke", said: "Struggling", rank: 0 },
  cordoned: { mood: "waiting", said: "Cordoned", rank: 1 },
  draining: { mood: "waiting", said: "Finishing up", rank: 2 },
  full: { mood: "waiting", said: "Full", rank: 3 },
  taking: { mood: "held", said: "Taking calls", rank: 4 },
  gone: { mood: "none", said: "Not heard from", rank: 5 },
};

const keyOf = (worker: Worker): string => `${worker.fleet}/${worker.worker}`;
const calls = (many: number): string => `${count(many)} ${many === 1 ? "call" : "calls"}`;
const workers = (many: number): string => `${count(many)} ${many === 1 ? "worker" : "workers"}`;

function failing(worker: Worker): boolean {
  const ended = worker.ended ?? 0;
  if (ended >= ENDED_TO_JUDGE && (worker.failed ?? 0) / ended >= FAILED_SHARE) return true;
  const slow = worker.first_audio_p95_s;
  return (worker.turns ?? 0) >= TURNS_TO_JUDGE && slow != null && slow > SLOW_FIRST_AUDIO_S;
}

function stateOf(worker: Worker, fleet: TheFleet): State {
  if (fleet.now - worker.seen_at > fleet.stale_after_s) return "gone";
  if (worker.cordoned) return "cordoned";
  if (worker.draining) return "draining";
  if (failing(worker)) return "struggling";
  return worker.load >= (worker.max_jobs == null ? FULL_BY_LOAD : 1) ? "full" : "taking";
}

/** `1 of 2 calls in progress`; a worker with no count of seats says how busy its machine is. */
function holding(worker: Worker): string {
  if (worker.max_jobs == null) return `${calls(worker.active)} in progress, machine ${Math.round(Math.min(1, worker.load / FULL_BY_LOAD) * 100)}% busy`;
  return `${count(worker.active)} of ${calls(worker.max_jobs)} in progress`;
}

// A worker's LiveKit name ends in the second it started.
function startedAt(worker: Worker): number | null {
  const found = /\.(\d{9,})$/.exec(worker.agent_name ?? "");
  return found?.[1] === undefined ? null : Number(found[1]);
}

/** What the state means, in a sentence, for the panel's top. */
function meaning(worker: Worker, state: State): string {
  if (state === "gone") return worker.active > 0 ? `It went silent holding ${calls(worker.active)}. If it died, each caller hears one sentence and gets a call back.` : "It stopped reporting, as a worker does when a deploy replaces it. It leaves this list an hour after its last report.";
  if (state === "cordoned") return worker.active > 0 ? `It takes no new call and is finishing the ${calls(worker.active)} it holds.` : "It takes no new call and holds none.";
  if (state === "draining") return `It was told to stop, as in a deploy: no new call, and up to ten minutes to finish ${worker.active > 0 ? `the ${calls(worker.active)} it holds` : "what it holds"}.`;
  if (state === "struggling") return "Its last minute was bad: calls ended in errors, or callers waited over five seconds for a reply. New calls go to the other workers while one of them is well.";
  if (state === "full") return "Every seat is taken. It takes the next call when one ends.";
  return "It is answering calls.";
}

interface Environment {
  fleet: string;
  name: string;
  rows: Worker[];
  totals: FleetTotals;
}

function environmentsOf(fleet: TheFleet, names: FleetNames | null): Environment[] {
  const known = names === null ? [] : [names.production, names.sandbox];
  const fleets = [...new Set([...known, ...fleet.totals.map((one) => one.fleet), ...fleet.workers.map((one) => one.fleet)])];
  return fleets.map((named) => {
    const rows = fleet.workers.filter((one) => one.fleet === named).sort((one, other) => STANDING[stateOf(one, fleet)].rank - STANDING[stateOf(other, fleet)].rank || one.worker.localeCompare(other.worker));
    const heard = rows.filter((one) => stateOf(one, fleet) !== "gone");
    const taking = heard.filter((one) => ["taking", "struggling"].includes(stateOf(one, fleet)));
    const seats = heard.reduce((sum, one) => sum + (one.max_jobs ?? 0), 0);
    const active = heard.reduce((sum, one) => sum + one.active, 0);
    // The gateway's own sums when it says them; a gateway from before them leaves the page to add up.
    const totals = fleet.totals.find((one) => one.fleet === named) ?? { fleet: named, workers: heard.length, active, seats, free: Math.max(0, seats - active), accepting: taking.length, full: heard.length > 0 && taking.length === 0, waiting: 0 };
    return { fleet: named, name: names?.production === named ? "Production" : names?.sandbox === named ? "Sandbox" : named, rows, totals };
  });
}

interface Issue {
  tone: "bad" | "warn";
  text: string;
  /** The worker to open, when the thing to act on is one worker. */
  worker?: string;
}

/** What needs a look, the worst first: callers nobody answers, then a worker that is unwell, then what was set aside. */
function issuesOf(environments: readonly Environment[], fleet: TheFleet): Issue[] {
  const bad: Issue[] = [];
  const warn: Issue[] = [];
  for (const one of environments) {
    if (one.totals.waiting > 0) bad.push({ tone: "bad", text: `${one.name}: ${count(one.totals.waiting)} ${one.totals.waiting === 1 ? "caller was" : "callers were"} left waiting for a worker in the last ten minutes.` });
    if (one.totals.workers === 0) bad.push({ tone: "bad", text: `${one.name}: no worker is reporting, so nobody answers its calls.` });
    else if (one.totals.accepting === 0) bad.push({ tone: "bad", text: `${one.name}: no worker is taking new calls. A phone caller hears one sentence and gets a call back.` });
    else if (one.totals.full) bad.push({ tone: "bad", text: `${one.name} is full: every seat is taken until a call ends.` });
    for (const worker of one.rows) {
      const state = stateOf(worker, fleet);
      const key = keyOf(worker);
      if (state === "struggling") warn.push({ tone: "warn", text: `${one.name}: ${worker.worker} is struggling. Open it to see its last minute, and cordon it if it stays so.`, worker: key });
      if (state === "gone" && worker.active > 0) warn.push({ tone: "warn", text: `${one.name}: ${worker.worker} went silent ${ago(worker.seen_at, fleet.now)} holding ${calls(worker.active)}.`, worker: key });
      if (state === "cordoned") warn.push({ tone: "warn", text: `${one.name}: ${worker.worker} is cordoned and takes no new call until you lift it.`, worker: key });
    }
  }
  return [...bad, ...warn];
}

function WorkerPanel({ worker, fleet, environment, onMoved, onClose }: { worker: Worker; fleet: TheFleet; environment: string; onMoved: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const mover = useMove();
  const state = stateOf(worker, fleet);
  const standing = STANDING[state];
  const started = startedAt(worker);
  const ended = worker.ended ?? null;
  const set = (wanted: boolean): void => void mover.move(() => cordon(credentials, worker, wanted).then(onMoved)).catch(() => undefined);
  return (
    <SidePanel
      title={worker.worker}
      icon="server"
      about={`A worker of ${environment}: a process that answers its calls.`}
      onClose={onClose}
      footer={
        <>
          {mover.refused !== null && <p className="cfg-refused">{mover.refused}</p>}
          <div className="cfg-dialog-foot">
            {worker.cordoned ? (
              <button type="button" className="cfg-save" disabled={mover.busy} onClick={() => set(false)}>
                {mover.busy ? "Lifting…" : "Lift the cordon"}
              </button>
            ) : (
              <ConfirmButton label="Cordon this worker" asks={worker.active > 0 ? `Stop new calls to it? Its ${calls(worker.active)} go on` : "Stop new calls to it?"} danger onConfirm={() => set(true)} />
            )}
          </div>
        </>
      }
    >
      <div className={`tst-last ${standing.mood === "held" ? "tst-last-held" : standing.mood === "broke" ? "tst-last-broke" : ""}`}>
        <span className="tst-last-top">
          <b>{standing.said}</b>
          <span className="dash-quiet">Heard from {ago(worker.seen_at, fleet.now)}</span>
        </span>
        <span className="tst-last-why">{meaning(worker, state)}</span>
      </div>

      <dl className="tst-facts">
        <div>
          <dt>Calls</dt>
          <dd>{holding(worker)}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{started === null ? "Still starting up: it is offered no call yet" : ago(started, fleet.now)}</dd>
        </div>
        {worker.version != null && (
          <div>
            <dt>Version</dt>
            <dd>{worker.version}</dd>
          </div>
        )}
        <div>
          <dt>Its last minute</dt>
          <dd>{ended === null ? "Not reported by this worker" : ended === 0 ? "No call ended" : `${calls(ended)} ended, ${count(worker.failed ?? 0)} with an error`}</dd>
        </div>
        {worker.first_audio_p95_s != null && (
          <div>
            <dt>Slowest replies</dt>
            <dd>
              {worker.first_audio_p95_s.toFixed(1)} s before the caller heard an answer, over {count(worker.turns ?? 0)} turns
            </dd>
          </div>
        )}
        <div>
          <dt>Fleet</dt>
          <dd>{worker.fleet}</dd>
        </div>
      </dl>

      {worker.agent_name != null && (
        <Field label="Its name on LiveKit">
          <Copy text={worker.agent_name} bare />
        </Field>
      )}

      <Field label={worker.cordoned ? "Lifting the cordon" : "What a cordon does"}>
        {worker.cordoned ? (
          <p className="flt-says">It is offered calls again within about five seconds. Nothing else changes.</p>
        ) : (
          <ul className="flt-says flt-points">
            <li>It is offered no new call, from its next report, about five seconds away.</li>
            <li>{worker.active > 0 ? `The ${calls(worker.active)} it holds go on to their end. No caller is cut off.` : "It holds no call now, so no caller notices."}</li>
            <li>{environment} has that much less room until you lift the cordon. On a cluster the worker restarts once empty and stays cordoned.</li>
          </ul>
        )}
      </Field>
    </SidePanel>
  );
}

function Share({ worker, state }: { worker: Worker; state: State }): ReactNode {
  const filled = state === "gone" ? 0 : Math.min(1, Math.max(0, worker.max_jobs == null ? worker.load / FULL_BY_LOAD : worker.load));
  return (
    <span className="tst-bar flt-bar" aria-hidden="true">
      {filled > 0 && <i className={filled >= 1 ? "flt-fill flt-fill-full" : "flt-fill"} style={{ flexGrow: filled }} />}
      {filled < 1 && <i className="tst-bar-none" style={{ flexGrow: 1 - filled }} />}
    </span>
  );
}

function Total({ label, value, under, mood }: { label: string; value: string; under: string; mood?: "bad" | undefined }): ReactNode {
  return (
    <div className="flt-total">
      <span className="dash-eyebrow">{label}</span>
      <span className={mood === "bad" ? "dash-big dash-mood-bad" : "dash-big"}>{value}</span>
      <span className="dash-quiet">{under}</span>
    </div>
  );
}

function Fleet(): ReactNode {
  const credentials = useCredentials();
  const [fleet, setFleet] = useState<TheFleet | null>(null);
  const [names, setNames] = useState<FleetNames | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);

  const reread = useCallback(
    (): Promise<void> =>
      readFleet(credentials).then(
        (read) => (setFleet(read), setRefused(null)),
        (failed: unknown) => setRefused(saidBy(failed)),
      ),
    [credentials],
  );

  useFed(() => void reread(), { door: "/v1/ops/events", types: A_WORKER_CHANGED }, [reread]);

  useEffect(() => {
    // Without the names the sections are still drawn, under each fleet's own name.
    readFleetNames(credentials).then(setNames, () => undefined);
    const timer = window.setInterval(() => {
      if (!document.hidden) void reread();
    }, REREAD_MS);
    return () => window.clearInterval(timer);
  }, [credentials, reread]);

  const environments = fleet === null ? [] : environmentsOf(fleet, names);
  const issues = fleet === null ? [] : issuesOf(environments, fleet);
  const worst = issues.some((one) => one.tone === "bad") ? "bad" : issues.length > 0 ? "warn" : "good";
  const active = environments.reduce((sum, one) => sum + one.totals.active, 0);
  const seats = environments.reduce((sum, one) => sum + one.totals.seats, 0);
  const free = environments.reduce((sum, one) => sum + one.totals.free, 0);
  const taking = environments.reduce((sum, one) => sum + one.totals.accepting, 0);
  const heard = environments.reduce((sum, one) => sum + one.totals.workers, 0);
  const waiting = environments.reduce((sum, one) => sum + one.totals.waiting, 0);
  const picked = open === null ? undefined : fleet?.workers.find((one) => keyOf(one) === open);
  const pickedIn = picked === undefined ? undefined : environments.find((one) => one.fleet === picked.fleet);

  return (
    <div className="tst flt">
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      {fleet === null && refused === null && <p className="dash-quiet">Reading…</p>}

      {fleet !== null && (
        <>
          <section className={`dash-card flt-lead flt-lead-${worst}`} aria-label="How the fleet stands">
            <div className="flt-verdict">
              <span className="flt-dot" aria-hidden="true" />
              <span className="flt-verdict-words">
                <span className="flt-verdict-title">{worst === "good" ? "Everything is fine" : worst === "warn" ? "Calls are being answered, with something to look at" : "Callers are affected"}</span>
                <span className="dash-quiet">{worst === "good" ? `Every environment is answering calls, with room for ${calls(free)} more.` : issues.length === 1 ? "One thing, below." : `${count(issues.length)} things, the most pressing first.`}</span>
              </span>
            </div>
            {issues.length > 0 && (
              <ol className="flt-issues">
                {issues.map((one, at) => (
                  <li key={at} className={`flt-issue flt-issue-${one.tone}`}>
                    <span className="flt-issue-text">{one.text}</span>
                    {one.worker !== undefined && (
                      <button type="button" className="app-button" onClick={() => setOpen(one.worker ?? null)}>
                        Open it
                      </button>
                    )}
                  </li>
                ))}
              </ol>
            )}
            <div className="flt-totals">
              <Total label="Calls in progress" value={count(active)} under={seats > 0 ? `of ${count(seats)} at once` : "right now"} />
              <Total label="Room left" value={count(free)} under={free === 1 ? "more call can start" : "more calls can start"} mood={heard > 0 && free === 0 ? "bad" : undefined} />
              <Total label="Workers taking calls" value={count(taking)} under={`of ${count(heard)} reporting`} mood={taking === 0 ? "bad" : undefined} />
              <Total label="Callers left waiting" value={count(waiting)} under="in the last ten minutes" mood={waiting > 0 ? "bad" : undefined} />
            </div>
          </section>

          {environments.map((one) => (
            <section key={one.fleet} className="tst-list" aria-label={one.name}>
              <header className="tst-head">
                <span className="tst-head-mark" aria-hidden="true">
                  <Icon name="server" size={16} />
                </span>
                <span className="tst-head-words">
                  <span className="tst-head-title">{one.name}</span>
                  <span className="tst-head-about">{one.totals.workers === 0 ? "No worker is reporting here." : `${workers(one.totals.workers)} reporting. ${count(one.totals.active)} of ${calls(one.totals.seats)} in progress, room for ${count(one.totals.free)} more.`}</span>
                </span>
                <span className="tst-head-stands">
                  {count(one.totals.accepting)} of {count(one.totals.workers)} taking calls
                </span>
              </header>
              {one.rows.length === 0 && <p className="dash-quiet tst-none">No worker has reported in the last hour.</p>}
              {one.rows.map((worker) => {
                const state = stateOf(worker, fleet);
                const standing = STANDING[state];
                const started = startedAt(worker);
                const key = keyOf(worker);
                return (
                  <div key={key} className={`tst-row${open === key ? " tst-row-on" : ""}${state === "gone" ? " flt-gone" : ""}`}>
                    <button type="button" className="tst-row-main" onClick={() => setOpen(key)}>
                      <span className="tst-mark" aria-hidden="true">
                        <Icon name="server" size={14} />
                      </span>
                      <span className="tst-row-words">
                        <span className="tst-row-name">
                          <span className="dash-clip flt-name">{worker.worker}</span>
                          {worker.version != null && <span className="tst-tag">{worker.version}</span>}
                        </span>
                        <span className="tst-row-under dash-clip">
                          {state === "gone" ? `Last held ${calls(worker.active)}` : holding(worker)}
                          {started !== null && `, started ${ago(started, fleet.now)}`}
                        </span>
                      </span>
                      <Share worker={worker} state={state} />
                      <span className="tst-row-when flt-when">Heard {ago(worker.seen_at, fleet.now)}</span>
                      <span className={`tst-status flt-status tst-status-${standing.mood}`}>{standing.said}</span>
                    </button>
                  </div>
                );
              })}
            </section>
          ))}
        </>
      )}

      {picked !== undefined && fleet !== null && <WorkerPanel key={keyOf(picked)} worker={picked} fleet={fleet} environment={pickedIn?.name ?? picked.fleet} onMoved={reread} onClose={close} />}
    </div>
  );
}

/** Nothing is asked of the gateway for a person who does not run the deployment. */
export function FleetPage(): ReactNode {
  const { whose } = useOrg();
  return (
    <>
      <PageHead />
      {whose !== null && (whose.operator === true ? <Fleet /> : <p className="dash-quiet">This page is the operator's: the person who runs this deployment.</p>)}
    </>
  );
}
