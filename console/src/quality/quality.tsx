/** Quality: how the real calls kept their rules over a window, with the share that held, what broke, the fixes ready, each judge, and the calls that broke one. */

import { useCallback, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { count, percent, utcDay } from "../lib/format";
import { useFleet } from "../dashboard/fleet";
import { useInsights } from "../lib/insights";
import { useOrg } from "../lib/org";
import { PageHead } from "../shell/page-head";
import { Select } from "../ui/select";
import { fixable, Fixes } from "./fixes";
import { Hero, type Figure } from "./hero";
import { JudgePanel } from "./judge-panel";
import { BrokenCalls, ByAgent, Judges } from "./judges";
import { NothingJudged } from "./nothing";
import { useCases, useJudges, useSuites } from "./reads";
import { brokenCalls, judgedIn, rulesOf } from "./rules";
import { useScores } from "./use-scores";
import { useOpeningWindow, useWidenedWhenQuiet, WINDOWS } from "./window";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../calls/calls.css";
import "./quality.css";

const AGENT = "agent";
const JUDGE = "judge";

// The agents the org has now: the ones Agents and Apps list. Until 0.11.39 this page also listed every
// name a call of the window carried, so an app removed weeks ago was still an agent here.
function useTheAgentsThereAre(): ReadonlySet<string> {
  const { studio, code } = useFleet();
  return useMemo(() => new Set([...studio, ...code].map((one) => one.agent)), [studio, code]);
}

/** The agent whose calls are read, when the org has several: the agents there are, never one that was removed. */
function AgentPick({ agent, onPick }: { agent: string; onPick: (agent: string) => void }): ReactNode {
  const slugs = [...useTheAgentsThereAre()].sort();
  if (slugs.length < 2) return null;
  return (
    <div className="ql-pick">
      <Select label="Whose calls" value={agent} items={[{ value: "", label: "Every agent" }, ...slugs.map((slug) => ({ value: slug, label: slug }))]} onChange={onPick} />
    </div>
  );
}

/**
 * The window's numbers are the gateway's count; each judge's rate and the calls it broke are read
 * off the newest judged calls, one log each: the window counts every call, the judges what was
 * read. Unless a window was picked the page opens on the week, and on the month when the week
 * judged nothing; a window with no verdict draws one card saying so.
 */
function Quality({ agent, open, ask }: { agent: string; open: string | null; ask: (name: string, value: string) => void }): ReactNode {
  const opening = useOpeningWindow();
  const { days } = opening;
  const whose = agent === "" ? {} : { agent };
  const earlier = useMemo(() => utcDay(Date.now() / 1000 - days * 86400), [days]);
  const answered = useInsights(days, whose);
  const answeredBefore = useInsights(days, { ...whose, day: earlier });
  const { lines } = useOrg();
  const mine = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const scored = useScores(mine);
  const judges = useJudges(agent);
  const cases = useCases(agent);
  const suites = useSuites().filter((suite) => agent === "" || suite.agent === agent);

  // Nothing is drawn of another window than the one picked.
  const counted = answered?.days === days ? answered : null;
  const there = useTheAgentsThereAre();
  // By agent, the ones the org still has and whose calls were judged: a removed app's score is history, not a row.
  const scoredNow = useMemo(() => (counted?.agents ?? []).filter((one) => one.score !== null && there.has(one.slug)), [counted, there]);
  const before = answeredBefore?.days === days ? answeredBefore : null;
  const quiet = counted === null ? null : counted.judged === 0;
  const deciding = useWidenedWhenQuiet(opening, quiet);

  const rules = rulesOf(judges, scored);
  const rule = open === null ? undefined : rules.find((one) => one.name === open);
  const fixes = (cases.groups ?? []).filter(fixable);
  const held = suites.reduce((all, suite) => all + suite.held, 0);
  const cells = suites.reduce((all, suite) => all + suite.cells, 0);
  const calls = agent === "" ? "/calls" : `/calls?agent=${encodeURIComponent(agent)}`;
  const brokeInCalls = `/calls?status=broke${agent === "" ? "" : `&agent=${encodeURIComponent(agent)}`}`;
  const close = useCallback(() => ask(JUDGE, ""), [ask]);

  const broke = counted === null ? 0 : counted.judged - counted.passed;
  const total = counted?.conversations.now ?? 0;
  const figures: Figure[] = [
    { title: "Judged", value: counted === null || total === 0 ? "—" : percent(Math.min(1, counted.judged / total)), under: counted === null ? "" : `${count(counted.judged)} of ${count(total)} calls`, to: calls },
    { title: "Calls that broke", value: String(broke), under: broke === 1 ? "It broke a rule" : "They broke a rule", mood: broke > 0 ? "bad" : undefined, to: brokeInCalls },
    { title: "Fixes ready", value: cases.groups === null ? "—" : String(fixes.length), under: fixes.length === 0 ? "Nothing diagnosed waits" : "One move each, below" },
    { title: "To a person", value: counted === null ? "—" : count(counted.escalated), under: total === 0 || counted === null ? "No calls" : `${percent(counted.escalated / total)} of the calls` },
    { title: "Goldens", value: cells === 0 ? "—" : `${held}/${cells}`, under: cells === 0 ? "No run yet" : "Held in the last run", mood: cells === 0 ? undefined : held === cells ? "good" : "warn" },
  ];

  return (
    <>
      <PageHead>
        <AgentPick agent={agent} onPick={(picked) => ask(AGENT, picked)} />
        <div className="dash-switch" role="group" aria-label="Window">
          {WINDOWS.map((one) => (
            <button key={one.days} type="button" aria-pressed={one.days === days} className={one.days === days ? "dash-switch-on" : ""} onClick={() => opening.pick(one.days)}>
              {one.name}
            </button>
          ))}
        </div>
      </PageHead>
      <div className="ql">
        {deciding || counted === null ? (
          <p className="dash-quiet">Counting the verdicts…</p>
        ) : quiet === true ? (
          <NothingJudged days={days} judging={judges === null ? null : judges.some((judge) => judge.on)} calls={calls} onWiden={days === 30 ? null : () => opening.pick(30)} />
        ) : (
          <>
            <Hero counted={counted} before={before} days={days} figures={figures} />
            <Fixes groups={fixes} everyAgent={agent === ""} />
            {agent === "" && scoredNow.length > 1 && <ByAgent agents={scoredNow} onPick={(picked) => ask(AGENT, picked)} />}
            <div className="ql-pair">
              <Judges rules={rules} read={judgedIn(scored)} open={rule?.name ?? null} onOpen={(name) => ask(JUDGE, name === rule?.name ? "" : name)} />
              <BrokenCalls calls={brokenCalls(scored)} to={brokeInCalls} />
            </div>
          </>
        )}
      </div>
      {rule !== undefined && <JudgePanel key={rule.name} rule={rule} scored={scored} cases={cases.cases} onClose={close} />}
    </>
  );
}

/** The address says whose calls (`?agent=`), over which window (`?days=`) and which judge is open (`?judge=`). */
export function QualityPage(): ReactNode {
  const [params, setParams] = useSearchParams();
  const ask = useCallback(
    (name: string, value: string): void => {
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          if (value === "") next.delete(name);
          else next.set(name, value);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const agent = params.get(AGENT) ?? "";
  // One page per agent in view: nothing read for one is ever drawn for another.
  return <Quality key={agent} agent={agent} open={params.get(JUDGE)} ask={ask} />;
}
