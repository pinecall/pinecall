/** Play a case again on a version of the agent's settings, and read the replay as a transcript: where it held, where it broke. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import type { TuningRow } from "@pinecall/core/wire/rest-org";
import { ago } from "../../lib/format";
import { inTheWorld, WORLD } from "../../lib/mode";
import { Button, Select, SelectItem } from "../../ui";
import { readGolden, readRun, runCases, StateMark, Transcript, type EvalRun } from "../evals";
import { readHistory } from "../settings";
import type { EvalCase } from "./door";
import { Section } from "./section";

// The Select's value for "no version named": the corner as it stands.
const AS_IT_STANDS = "";

const HINT = "In the sandbox, through the agent pinecall start holds.";

export function CaseRun({ agent, kept }: { agent: string; kept: EvalCase }): ReactNode {
  if (WORLD === "production") {
    const there = inTheWorld("sandbox", `/a/${encodeURIComponent(agent)}/cases/${encodeURIComponent(kept.name)}`);
    return (
      <Section title="Run it" hint={HINT}>
        <a className="cs-elsewhere" href={there}>
          Open this case in the sandbox to run it →
        </a>
      </Section>
    );
  }
  return <RunInTheSandbox agent={agent} kept={kept} />;
}

function RunInTheSandbox({ agent, kept }: { agent: string; kept: EvalCase }): ReactNode {
  const credentials = useCredentials();
  const [versions, setVersions] = useState<TuningRow[]>([]);
  const [version, setVersion] = useState(AS_IT_STANDS);
  const [starting, setStarting] = useState(false);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
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

  // Your own corner's versions: what a fix in the settings is saved as before anybody else hears it.
  useEffect(() => {
    let live = true;
    readHistory(credentials, agent, false)
      .then((read) => live && setVersions(read.rows))
      .catch(() => live && setVersions([]));
    return () => {
      live = false;
    };
  }, [credentials, agent]);

  const play = async (): Promise<void> => {
    setStarting(true);
    setRefused(null);
    setRun(null);
    try {
      setRun(await runCases(credentials, agent, [kept.name], version === AS_IT_STANDS ? undefined : Number(version)));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setStarting(false);
    }
  };
  const cell = run?.matrix?.runs[0];
  const holds = cell !== undefined && cell.scores.every((score) => score.passed);

  return (
    <Section title="Run it" hint={HINT}>
      <div className="cs-run">
        <Select value={version} onValueChange={setVersion} aria-label="Settings version">
          <SelectItem value={AS_IT_STANDS}>Your settings as they stand</SelectItem>
          {versions.map((row) => (
            <SelectItem key={row.version} value={String(row.version)}>
              v{row.version} · {row.note ?? "no note"} · {ago(row.set_at)}
            </SelectItem>
          ))}
        </Select>
        <Button kind="primary" size="sm" disabled={running} onClick={() => void play()}>
          {running ? "Playing the caller…" : "Run it"}
        </Button>
      </div>
      {refused !== null && (
        <p className="cs-bad">
          {refused}
          {/no app|holds the agent|nobody/i.test(refused) && " — start the agent with pinecall start in its directory, then run it again."}
        </p>
      )}
      {run !== null && cell === undefined && <p className="cs-bad">{run.error ?? "The run judged nothing."}</p>}
      {cell !== undefined && (
        <div className="cs-result">
          <p className="cs-result-head">
            <StateMark state={holds ? "held" : "broke"} />
            <span>
              {holds ? "Approve it, and the nightly keeps it holding." : "Reproduced. Fix it, then run it again."}{" "}
              {run?.calls[0] !== undefined && <a href={inTheWorld("sandbox", `/calls/${encodeURIComponent(run.calls[0].call)}`)}>The call it made →</a>}
            </span>
          </p>
          <Transcript read={readGolden(kept.golden, cell.scores)} />
        </div>
      )}
    </Section>
  );
}
