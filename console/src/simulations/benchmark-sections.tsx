/** What a benchmark says around its board: over it the two bars and the verdict against them, under it the judges, the rounds, the calls that failed and the ones that do not count. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import type { Bars, BenchCall, NotCounted, Standings } from "@pinecall/agents/evals";
import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { setupName, type Comparison } from "./door";
import { reportOf, saveReport } from "./report";

const WHOSE: Record<NotCounted["kind"], string> = { vendor: "A vendor failed it", platform: "The platform lost it", caller: "Its caller broke" };

const sentence = (words: string): string => `${words.charAt(0).toUpperCase()}${words.slice(1)}.`;

/** A bar as a person types it: kept as typed, and told on only when it is a number the bar may be. */
function BarField({ label, unit, value, step, most, onValue }: { label: string; unit: string; value: number; step: number; most: number; onValue: (value: number) => void }): ReactNode {
  const [typed, setTyped] = useState(String(value));
  return (
    <label className="cmp-bar">
      <span>{label}</span>
      <input
        className="cfg-input"
        type="number"
        inputMode="decimal"
        min={step}
        max={most}
        step={step}
        value={typed}
        onChange={(event) => {
          setTyped(event.target.value);
          const asked = Number(event.target.value);
          if (event.target.value !== "" && Number.isFinite(asked) && asked > 0 && asked <= most) onValue(asked);
        }}
      />
      <span>{unit}</span>
    </label>
  );
}

/** The two bars every setup is held to, what the benchmark says against them, and the report as a file. */
export function TheBars({ tables, made, bars, onBars, going }: { tables: readonly Comparison[]; made: Standings; bars: Bars; onBars: (bars: Bars) => void; going: boolean }): ReactNode {
  const credentials = useCredentials();
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const counted = made.calls.filter((call) => call.not_counted === null).length;
  const passed = made.verdict.passed;

  const download = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      saveReport(await reportOf(credentials, tables, bars));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="dash-card cmp-bars" aria-label="The bars">
      <div className="dash-card-top">
        <span className="dash-eyebrow">The benchmark</span>
        <button type="button" className="app-button" disabled={saving || made.calls.length === 0} title="The same report pinecall benchmark writes, with each call's lines" onClick={() => void download()}>
          {saving ? "Reading every call…" : "Download report.json"}
        </button>
      </div>
      <p className={passed === null ? "cmp-said" : passed ? "cmp-said cmp-said-passed" : "cmp-said cmp-said-failed"} role="status">
        {made.calls.length === 0
          ? "No call has ended yet."
          : passed === null
            ? "Nobody judged a call: a caller that expects something, and the judge of it, say whether its call was completed."
            : sentence(made.verdict.says)}
      </p>
      <div className="cmp-bars-row">
        <BarField label="Calls completed, at least" unit="%" value={Math.round(bars.floor * 100)} step={1} most={100} onValue={(percent) => onBars({ ...bars, floor: percent / 100 })} />
        <BarField label="A typical reply within" unit="s" value={bars.ceiling_s} step={0.1} most={60} onValue={(seconds) => onBars({ ...bars, ceiling_s: seconds })} />
        <span className="dash-quiet">
          {going ? `Of the ${counted} calls that count so far.` : `Of ${counted} calls that count`}
          {!going && made.calls.length > counted && `, ${made.calls.length - counted} left out`}
          {!going && "."}
        </span>
      </div>
      {refused !== null && <p className="app-refused">{refused}</p>}
    </section>
  );
}

/** One call as a row that opens it: its caller, the setup it was under, and what is said of it. */
function CallRow({ call, names, said }: { call: BenchCall; names: ReadonlyMap<string, string>; said: ReactNode }): ReactNode {
  return (
    <Link to={`/simulations/${call.call}`} className="dash-row cmp-call">
      <span className="cmp-call-who dash-clip">{call.caller}</span>
      <span className="dash-quiet dash-clip">
        {names.get(call.setup) ?? call.setup}
        {call.round > 1 && ` · round ${call.round}`}
      </span>
      <span className="cmp-call-why">{said}</span>
    </Link>
  );
}

/** Under the board: each judge by setup, each round by setup, the counted calls that failed with the judge's reason, and the calls in no number with why. */
export function UnderTheBoard({ made }: { made: Standings }): ReactNode {
  const names = new Map(made.setups.map((one) => [one.name, setupName(one.values)]));
  const columns = { gridTemplateColumns: `minmax(140px, 1.1fr) repeat(${made.setups.length}, minmax(160px, 1fr))` };
  const judges = [...new Set(made.setups.flatMap((one) => one.judges.map((judge) => judge.name)))];
  const rounds = [...new Set(made.setups.flatMap((one) => one.rounds.map((round) => round.round)))].sort((one, other) => one - other);
  const failed = made.calls.filter((call) => call.not_counted === null && call.completed === false);
  const left = made.calls.filter((call) => call.not_counted !== null);
  const head = (
    <>
      {made.setups.map((one) => (
        <span key={one.name} className="cmp-col dash-clip">
          {names.get(one.name)}
        </span>
      ))}
    </>
  );

  return (
    <>
      {judges.length > 0 && (
        <section className="dash-card cmp-matrix" aria-label="Judges">
          <div className="cmp-grid" style={columns}>
            <span className="cmp-corner dash-quiet">Judge</span>
            {head}
            {judges.map((name) => (
              <div key={name} className="cmp-row">
                <span className="cmp-task dash-clip">{name}</span>
                {made.setups.map((one) => {
                  const judge = one.judges.find((mine) => mine.name === name);
                  const answered = judge === undefined ? 0 : judge.held + judge.broken;
                  return (
                    <span key={one.name} className={judge !== undefined && judge.broken > 0 ? "cmp-count cmp-count-low" : "cmp-count"}>
                      {judge === undefined || answered === 0 ? "—" : `${judge.held} of ${answered} held`}
                      {judge !== undefined && judge.other > 0 && <small> · {judge.other} without a verdict</small>}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="dash-quiet cmp-foot">What each judge said of the calls that count, a setup a column.</p>
        </section>
      )}

      {rounds.length > 1 && (
        <section className="dash-card cmp-matrix" aria-label="Round by round">
          <div className="cmp-grid" style={columns}>
            <span className="cmp-corner dash-quiet">Round</span>
            {head}
            {rounds.map((round) => (
              <div key={round} className="cmp-row">
                <span className="cmp-task">Round {round}</span>
                {made.setups.map((one) => {
                  const its = one.rounds.find((mine) => mine.round === round);
                  return (
                    <span key={one.name} className={its !== undefined && its.completed < its.of ? "cmp-count cmp-count-low" : "cmp-count"}>
                      {its === undefined ? "—" : `${its.completed} of ${its.of}`}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="dash-quiet cmp-foot">A round is every caller rung once under a setup: how far one run of the same callers moves from the next.</p>
        </section>
      )}

      {made.calls.length > 0 && (
        <section className="dash-card" aria-label="Calls that failed">
          <div className="dash-card-top">
            <span className="dash-eyebrow">Calls that failed</span>
            <span className="dash-quiet">{failed.length === 0 ? "" : `${failed.length} of the calls that count`}</span>
          </div>
          {failed.length === 0 ? (
            <p className="dash-quiet">No call that counts failed.</p>
          ) : (
            <div className="dash-rows">
              {failed.map((call) => (
                <CallRow key={call.call} call={call} names={names} said={call.reason ?? "The judge gave no reason."} />
              ))}
            </div>
          )}
        </section>
      )}

      {left.length > 0 && (
        <section className="dash-card" aria-label="Calls not counted">
          <div className="dash-card-top">
            <span className="dash-eyebrow">Calls not counted</span>
            <span className="dash-quiet">In none of the numbers above</span>
          </div>
          <div className="dash-rows">
            {left.map((call) => (
              <CallRow
                key={call.call}
                call={call}
                names={names}
                said={
                  <>
                    <b>{WHOSE[call.not_counted?.kind ?? "platform"]}</b> · {call.not_counted?.why}
                  </>
                }
              />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
