/** One case open, in the page or over its group: what broke, the call as it is played again with what it checks, a run on a version of the settings, and what a person decides. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useCall } from "@pinecall/core/use-call";
import { useFed } from "@pinecall/core/use-fed";
import { type Entry } from "@pinecall/core/wire/envelope";
import { ago } from "../lib/format";
import { inWorld, WORLD } from "../lib/world";
import { decideCase } from "../test/door";
import { demandsOf, turnsOf } from "../test/fold";
import { Select } from "../ui/select";
import { Field, Fold, Setting, Toggle } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { playCase, readRun, readVersions, type CaseDecision, type EvalCase, type Run, type TuningRow } from "./door";
import { fromOf } from "./group";

const STANDS = { pending: "Waiting for you", approved: "A golden, played on every run", dismissed: "Dismissed" } as const;

// The Select's value for no version named: the settings as they stand.
const AS_THEY_STAND = "";

type Heard = { id: string; who: "caller" | "agent"; text: string } | { id: string; who: "tool"; text: string; failed: boolean };

function heardOf(entry: Entry): Heard | null {
  const data = entry.data as Record<string, unknown>;
  if (entry.type === "turn.user" || entry.type === "turn.agent") {
    const text = typeof data["text"] === "string" ? data["text"].trim() : "";
    return text === "" ? null : { id: `t${entry.seq}`, who: entry.type === "turn.user" ? "caller" : "agent", text };
  }
  if (entry.type === "tool.result") return { id: `x${entry.seq}`, who: "tool", text: String(data["name"]), failed: data["error"] !== undefined && data["error"] !== null };
  return null;
}

/** The conversation the case was kept from, read off that call's log. */
function Conversation({ call }: { call: string }): ReactNode {
  const [heard, setHeard] = useState<Heard[]>([]);
  const { error, connection } = useCall(call, {
    onEntry(entry) {
      const line = heardOf(entry);
      if (line !== null) setHeard((was) => (was.some((one) => one.id === line.id) ? was : [...was, line]));
    },
  });
  if (error !== null) return <p className="dash-quiet">That call's log could not be read.</p>;
  if (heard.length === 0) return <p className="dash-quiet">{connection === "connecting" ? "Reading the call…" : "Nothing was said on that call."}</p>;
  return (
    <div className="tst-heard">
      {heard.map((line) =>
        line.who === "tool" ? (
          <span key={line.id} className={line.failed ? "tst-heard-tool tst-heard-tool-bad" : "tst-heard-tool"}>
            {line.failed ? "✗" : "✓"} {line.text}
          </span>
        ) : (
          <p key={line.id} className={line.who === "caller" ? "tst-heard-line tst-heard-caller" : "tst-heard-line"}>
            {line.text}
          </p>
        ),
      )}
    </div>
  );
}

// One level of a state's objects opened into dotted names (`patient.name`), the rest said as JSON.
function flattened(state: Record<string, unknown>): [string, string][] {
  const said = (value: unknown): string => (typeof value === "string" ? value : JSON.stringify(value));
  return Object.entries(state).flatMap(([what, value]): [string, string][] => (value !== null && typeof value === "object" && !Array.isArray(value) ? Object.entries(value).map(([inner, held]): [string, string] => [`${what}.${inner}`, said(held)]) : [[what, said(value)]]));
}

/** The case played again, in the sandbox, through whatever holds the agent: a fix is proven here before the case is approved. */
function PlayIt({ kept }: { kept: EvalCase }): ReactNode {
  const credentials = useCredentials();
  const [versions, setVersions] = useState<TuningRow[]>([]);
  const [version, setVersion] = useState(AS_THEY_STAND);
  const [starting, setStarting] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const playing = starting || run?.status === "running";

  useEffect(() => {
    let gone = false;
    // A key that may not read the versions plays the settings as they stand.
    readVersions(credentials, kept.agent).then(
      (rows) => !gone && setVersions(rows),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, kept.agent]);

  // The gateway answers the run as it starts it: it is read again on each change until it is over.
  useFed(
    () => {
      if (run?.status !== "running") return;
      readRun(credentials, run.id).then(setRun, (failed: unknown) => setRefused(saidBy(failed)));
    },
    { types: ["run.changed"] },
    [run?.id, run?.status],
  );

  const play = async (): Promise<void> => {
    setStarting(true);
    setRefused(null);
    setRun(null);
    try {
      setRun(await playCase(credentials, kept.agent, kept.name, version === AS_THEY_STAND ? null : Number(version)));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setStarting(false);
    }
  };

  const cell = run?.matrix?.runs.find((one) => one.golden === kept.name);
  const broke = cell === undefined ? [] : cell.scores.filter((score) => !score.passed);
  const call = run?.calls.find((one) => one.golden === kept.name)?.call;
  const items = [{ value: AS_THEY_STAND, label: "Your settings as they stand" }, ...versions.map((row) => ({ value: String(row.version), label: `v${row.version}`, detail: `${row.note ?? "No note"} · ${ago(row.set_at)}` }))];

  return (
    <div className="cs-play">
      <div className="cs-play-ask">
        <Select label="On which settings" searchable={false} items={items} value={version} onChange={setVersion} />
        <button type="button" className="app-button cs-play-go" disabled={playing} onClick={() => void play()}>
          {playing ? "Playing…" : "Run it"}
        </button>
      </div>
      {refused !== null && <p className="app-refused">{refused}</p>}
      {run !== null && run.status !== "running" && cell === undefined && <p className="app-refused">{run.error ?? "The run judged nothing."}</p>}
      {cell !== undefined && (
        <div className={broke.length === 0 ? "tst-last tst-last-held" : "tst-last tst-last-broke"}>
          <span className="tst-last-top">
            <b>{broke.length === 0 ? "Held" : "Broke again"}</b>
            {call !== undefined && (
              <Link to={`/calls/${encodeURIComponent(call)}`} className="dash-more">
                The call it made
              </Link>
            )}
          </span>
          {broke.length === 0 ? (
            <span>{kept.status === "pending" ? "Keep it as a golden and every run holds the agent to it." : "The agent does what the case asks."}</span>
          ) : (
            <ul className="tst-reasons">
              {[...new Set(broke.map((score) => (score.reason === "" ? score.metric : score.reason)))].map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Decision({ kept, onDecided }: { kept: EvalCase; onDecided: (kept: EvalCase) => void }): ReactNode {
  const credentials = useCredentials();
  // Dismissing says why, so it opens a choice before it writes anything.
  const [dismissing, setDismissing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const decide = async (decision: CaseDecision): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      onDecided(await decideCase(credentials, kept.id, decision));
      setDismissing(false);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };
  const noted = note.trim() === "" ? {} : { note: note.trim() };

  return (
    <>
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      {dismissing && (
        <div className="cs-why">
          <input className="cfg-input" aria-label="Why" placeholder="Why, for the judge's calibration (optional)" value={note} onChange={(event) => setNote(event.target.value)} />
          {kept.broke.map((one) => (
            <button key={one.judge} type="button" className="app-button" disabled={busy} onClick={() => void decide({ status: "dismissed", judge_was_wrong: one.judge, ...noted })}>
              {one.judge} was wrong, it should have held
            </button>
          ))}
          <button type="button" className="app-button" disabled={busy} onClick={() => void decide({ status: "dismissed", ...noted })}>
            Not worth keeping
          </button>
        </div>
      )}
      <div className="cfg-dialog-foot">
        {kept.status === "pending" ? (
          <>
            <button type="button" className="app-button" aria-expanded={dismissing} disabled={busy} onClick={() => setDismissing(!dismissing)}>
              {dismissing ? "Cancel" : "Dismiss"}
            </button>
            <button type="button" className="cfg-save" disabled={busy} onClick={() => void decide({ status: "approved" })}>
              Keep as a golden
            </button>
          </>
        ) : (
          <button type="button" className="app-button" disabled={busy} onClick={() => void decide({ status: "pending" })}>
            Open it again
          </button>
        )}
      </div>
    </>
  );
}

/** Where the case stands and where it came from, in a line. */
function Standing({ kept }: { kept: EvalCase }): ReactNode {
  return (
    <>
      <span className={`cs-stands cs-stands-${kept.status}`}>{STANDS[kept.status]}</span> {fromOf(kept)} of {kept.agent}, {ago(kept.created_at)}, in {kept.source_env}
      {kept.source_version !== null && ` on settings v${kept.source_version}`}.{kept.kept_in_repo && " Also kept in the repository."}
    </>
  );
}

function CaseBody({ kept, onDecided }: { kept: EvalCase; onDecided: (kept: EvalCase) => void }): ReactNode {
  const credentials = useCredentials();
  const [where, setWhere] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const golden = kept.golden;
  const turns = turnsOf(golden);
  const demands = demandsOf(golden.expect);
  const state = flattened(golden.state ?? {});
  const memory = golden.memory ?? [];
  const hold = async (on: boolean): Promise<void> => {
    setRefused(null);
    try {
      onDecided(await decideCase(credentials, kept.id, { held_out: on }));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <>
      {kept.broke.length > 0 && (
        <div className="tst-last tst-last-broke">
          <ul className="tst-reasons">
            {kept.broke.map((one) => (
              <li key={one.judge}>
                <b>{one.judge}</b> {one.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Field label="The call, as it is played again">
        {(state.length > 0 || memory.length > 0 || golden.today != null) && (
          <dl className="ql-facts cs-opens">
            {state.map(([what, value]) => (
              <div key={what}>
                <dt>{what}</dt>
                <dd>{value}</dd>
              </div>
            ))}
            {memory.length > 0 && (
              <div>
                <dt>Remembers</dt>
                <dd>{memory.join(" · ")}</dd>
              </div>
            )}
            {golden.today != null && (
              <div>
                <dt>Today is</dt>
                <dd>{golden.today}</dd>
              </div>
            )}
          </dl>
        )}
        <ol className="tst-script">
          {turns.map((turn, at) => (
            <li key={at}>
              <span className="tst-script-turn">
                {turn.said}
                {turn.then.length > 0 && (
                  <ul className="tst-demands">
                    {turn.then.map((step, which) => (
                      <li key={which} className={`tst-demand tst-demand-${step.tone}`}>
                        {step.text}
                      </li>
                    ))}
                  </ul>
                )}
              </span>
            </li>
          ))}
        </ol>
      </Field>

      <Field label="By the end of the conversation">
        {demands.length === 0 ? (
          <p className="dash-quiet">Nothing is checked at the end yet. Edit it in the agent's Test tab to say what the agent must keep doing.</p>
        ) : (
          <ul className="tst-demands">
            {demands.map((one) => (
              <li key={one.text} className={`tst-demand tst-demand-${one.tone}`}>
                {one.text}
              </li>
            ))}
          </ul>
        )}
      </Field>

      <Field label="Run it">
        {WORLD === "sandbox" ? (
          <PlayIt key={kept.id} kept={kept} />
        ) : (
          <a className="dash-more" href={inWorld("sandbox", `/cases?agent=${encodeURIComponent(kept.agent)}&case=${encodeURIComponent(kept.id)}`)}>
            A case is played in the sandbox. Open this one there
          </a>
        )}
      </Field>

      <Fold title="Where the fix belongs" open={where} onToggle={() => setWhere(!where)} />
      {where && (
        <div className="cs-where">
          <p>
            <b>In the settings</b>, when it is a price, a policy, how the call opens or ends, what is remembered, or the model guessing and cutting people off. Save it in the agent's Configure tab: it is a new version of your own, no deploy. Run the case on that version above.
          </p>
          <Link to={`/agents/${encodeURIComponent(kept.agent)}/configure`} className="dash-more">
            Open {kept.agent}'s settings
          </Link>
          <p>
            <b>In the code</b>, when it did the wrong thing at a step, used a tool for the wrong thing, or slips the same way everywhere. In the agent's folder, play it on every save, then keep it beside the code:
          </p>
          <pre className="cs-fix-change">{`pinecall test --case ${kept.name} --watch\npinecall cases pull ${kept.name}`}</pre>
        </div>
      )}

      {kept.status === "approved" && <Setting icon="clock" title="Held out" about="Left out of Run all and of the nightly run. It is played only when you run it by itself." aside={<Toggle on={kept.held_out} label="Held out" onChange={(on) => void hold(on)} />} />}
      {refused !== null && <p className="app-refused">{refused}</p>}

      {/* A call's log is read in the world it was made in. */}
      {kept.source_call !== null && (
        <Field label="The conversation it came from">
          {kept.source_env === WORLD ? (
            <>
              <Conversation key={kept.source_call} call={kept.source_call} />
              <Link to={`/calls/${encodeURIComponent(kept.source_call)}`} className="dash-more">
                Open the call
              </Link>
            </>
          ) : (
            <a className="dash-more" href={inWorld(kept.source_env, `/calls/${encodeURIComponent(kept.source_call)}`)}>
              It was a {kept.source_env} call. Open it there
            </a>
          )}
        </Field>
      )}
    </>
  );
}

/** A case of a group, opened over its group. */
export function CasePanel({ kept, onDecided, onClose }: { kept: EvalCase; onDecided: (kept: EvalCase) => void; onClose: () => void }): ReactNode {
  return (
    <SidePanel title={kept.name} icon="cases" width={520} about={<Standing kept={kept} />} onClose={onClose} footer={<Decision kept={kept} onDecided={onDecided} />}>
      <CaseBody kept={kept} onDecided={onDecided} />
    </SidePanel>
  );
}

/** A case in no group: it is the page. */
export function CaseOpen({ kept, onDecided }: { kept: EvalCase; onDecided: (kept: EvalCase) => void }): ReactNode {
  return (
    <section className="dash-card cs-case" aria-label={kept.name}>
      <p className="cs-case-about">
        <Standing kept={kept} />
      </p>
      <div className="cs-case-decide">
        <Decision kept={kept} onDecided={onDecided} />
      </div>
      <CaseBody kept={kept} onDecided={onDecided} />
    </section>
  );
}
