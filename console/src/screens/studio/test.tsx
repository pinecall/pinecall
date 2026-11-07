/** The editor's Goldens: the conversations the agent must hold — written here by hand, or a call kept and approved — and Run, which plays them against the agent the gateway holds, each verdict under it. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { Button, Pill } from "../../ui";
import { CaseList, NewCase, useCases, type EvalCase } from "../cases";
import { readRun, runCases, type EvalRun } from "../evals";
import { Section } from "./section";
import { playable, resultsOf, tallyWords, type CaseResult } from "./testing";

export function TestSection({ agent }: { agent: string }): ReactNode {
  const credentials = useCredentials();
  const { listed, asking, written } = useCases(agent);
  const [writing, setWriting] = useState(false);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // A golden is one written here or a kept call somebody approved; one a judge kept that waits for a decision is the Cases screen's.
  const goldens = (listed?.cases ?? []).filter((kept) => kept.status === "approved");
  const toPlay = playable(goldens);
  const running = starting || run?.status === "running";

  // The gateway answers the run as it starts it: the row is read again on each change until it is over.
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
      setRun(await runCases(credentials, agent, toPlay.map((kept) => kept.name), undefined));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setStarting(false);
    }
  };

  const results = run === null || run.matrix === null ? [] : resultsOf(run.matrix);
  return (
    <Section
      title="Goldens"
      meta="conversations written down, and what the agent must do in each"
      action={
        <>
          <Button size="sm" disabled={writing} onClick={() => setWriting(true)}>
            New golden
          </Button>
          <Button size="sm" kind="primary" disabled={running || toPlay.length === 0} onClick={() => void play()}>
            {running ? "Playing…" : toPlay.length === 0 ? "Run" : `Run ${String(toPlay.length)} golden${toPlay.length === 1 ? "" : "s"}`}
          </Button>
        </>
      }
    >
      {writing && (
        <NewCase
          agent={agent}
          called="golden"
          onClose={() => setWriting(false)}
          onWritten={(kept) => {
            written(kept);
            setWriting(false);
          }}
        />
      )}
      {refused !== null && <p className="sto-wrong">{refused}</p>}
      {listed === null && <p className="sto-hint">{asking ?? "Asking the gateway…"}</p>}
      {listed !== null && goldens.length === 0 && (
        <p className="sto-hint">No golden yet. New golden writes one: what the caller says, line by line, and what the agent must do — say this, never say that, call this tool. Run plays every one against the agent.</p>
      )}
      {run !== null && run.status !== "running" && <p className={run.status === "failed" ? "sto-wrong" : "sto-said"}>{run.status === "failed" ? (run.error ?? "The run failed.") : tallyWords(results)}</p>}
      {goldens.length > 0 && <CaseList agent={agent} cases={goldens} under={(kept) => <Verdict kept={kept} run={run} results={results} />} />}
    </Section>
  );
}

// Under a golden's line: that it is held out, or what the run said of it.
function Verdict({ kept, run, results }: { kept: EvalCase; run: EvalRun | null; results: readonly CaseResult[] }): ReactNode {
  if (kept.held_out) return <p className="sto-test-under sto-hint">Held out: Run skips it.</p>;
  if (run === null) return null;
  if (run.status === "running") return <p className="sto-test-under sto-hint">Playing…</p>;
  const result = results.find((one) => one.name === kept.name);
  if (result === undefined || result.verdict === "not judged") return <p className="sto-test-under sto-hint">Not judged.</p>;
  return (
    <div className="sto-test-under">
      <Pill tone={result.verdict === "held" ? "green" : "red"} small>
        {result.verdict}
      </Pill>
      {result.verdict === "broke" && (
        <ul className="sto-test-reasons">
          {result.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
