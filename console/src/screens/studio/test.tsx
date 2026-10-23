/** The editor's Test: the agent's cases — one written here by hand — and Run, which plays them against the agent the gateway holds, each case's verdict under it. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { Button, Pill } from "../../ui";
import { CaseList, NewCase, useCases, type EvalCase } from "../cases";
import { readRun, runCases, type EvalRun } from "../evals";
import { Section } from "./section";
import { notPlayedBecause, playable, resultsOf, tallyWords, type CaseResult } from "./testing";

export function TestSection({ agent }: { agent: string }): ReactNode {
  const credentials = useCredentials();
  const { listed, asking, written } = useCases(agent);
  const [writing, setWriting] = useState(false);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const cases = listed?.cases ?? [];
  const toPlay = playable(cases);
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
      title="Test"
      meta="the agent's cases, played against it here"
      action={
        <>
          <Button size="sm" disabled={writing} onClick={() => setWriting(true)}>
            New case
          </Button>
          <Button size="sm" kind="primary" disabled={running || toPlay.length === 0} onClick={() => void play()}>
            {running ? "Playing…" : toPlay.length === 0 ? "Run" : `Run ${String(toPlay.length)} case${toPlay.length === 1 ? "" : "s"}`}
          </Button>
        </>
      }
    >
      {writing && (
        <NewCase
          agent={agent}
          onClose={() => setWriting(false)}
          onWritten={(kept) => {
            written(kept);
            setWriting(false);
          }}
        />
      )}
      {refused !== null && <p className="sto-wrong">{refused}</p>}
      {listed === null && <p className="sto-hint">{asking ?? "Asking the gateway…"}</p>}
      {listed !== null && cases.length === 0 && <p className="sto-hint">No case yet: New case writes one by hand — what the caller says, and what the agent must do.</p>}
      {listed !== null && cases.length > 0 && toPlay.length === 0 && <p className="sto-hint">Nothing to run: every case waits for a decision or is held out.</p>}
      {run !== null && run.status !== "running" && <p className={run.status === "failed" ? "sto-wrong" : "sto-said"}>{run.status === "failed" ? (run.error ?? "The run failed.") : tallyWords(results)}</p>}
      {cases.length > 0 && <CaseList agent={agent} cases={cases} under={(kept) => <Verdict kept={kept} run={run} results={results} />} />}
    </Section>
  );
}

// Under a case's line: why it is not played, or what the run said of it.
function Verdict({ kept, run, results }: { kept: EvalCase; run: EvalRun | null; results: readonly CaseResult[] }): ReactNode {
  const why = notPlayedBecause(kept);
  if (why !== null) return <p className="sto-test-under sto-hint">Not played: {why}.</p>;
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
