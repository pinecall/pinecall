/** Quality: how the REAL calls kept their rules over a window — the share that held, what broke, the fixes ready, the goldens — then each rule, and the calls the picked one broke. */

import { useMemo, useState, type ReactNode } from "react";
import { useParams } from "react-router";

import { utcDay } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { useInsights, useWindowDays, WindowPicker } from "../../lib/insights";
import { useOrg } from "../../lib/org";
import { useScores } from "../../lib/use-scores";
import { Page, PageHead } from "../../ui";
import { useCases } from "../cases";
import { useSuites } from "../evals";
import { fixable, Fixes } from "./fixes";
import { Count, Kept } from "./kept";
import { BrokeIt, Rules, rulesOf } from "./rules";
import { useJudges } from "./use-judges";
import "./quality.css";

/**
 * Quality is about calls that happened; whether a change is safe before it ships is Test's. The
 * window's numbers are the gateway's count (`/v1/insights`); the fixes are the case groups whose
 * diagnosis names a change; each rule's rate and the calls it broke are read off the newest
 * judged calls the page follows, one log each — the window counts every call, the rules what was read.
 */
export function Quality(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const asked = agent === "" ? undefined : agent;
  const [days, pickDays] = useWindowDays(7);
  const counted = useInsights({ agent: asked, days });
  const before = useInsights({ agent: asked, day: utcDay(Date.now() / 1000 - days * 86400), days });
  const { lines } = useOrg();
  const mine = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const scored = useScores(mine);
  const judges = useJudges(agent === "" ? null : agent).judges;
  const cases = useCases(agent);
  const suites = [...useSuites().values()].filter((suite) => agent === "" || suite.agent === agent);

  const rules = rulesOf(judges, scored);
  const [picked, setPicked] = useState<string | null>(null);
  // Unpicked, the rule that broke most is the one shown.
  const rule = rules.find((one) => one.name === picked) ?? rules[0];
  const fixes = (cases.groups ?? []).filter(fixable);
  const broke = counted === null ? null : counted.judged - counted.passed;
  const held = suites.reduce((all, suite) => all + suite.held, 0);
  const cells = suites.reduce((all, suite) => all + suite.cells, 0);

  return (
    <Page>
      <PageHead title="Quality" lede="Judges read every call and check it against your rules." actions={<WindowPicker days={days} onPick={pickDays} />} />

      <div className="qly-top">
        <Kept counted={counted?.days === days ? counted : null} before={before?.days === days ? before : null} days={days} />
        <div className="qly-counts">
          <Count label="Calls that broke" value={broke === null ? "—" : String(broke)} tone={broke !== null && broke > 0 ? "red" : undefined} sub="a rule" to={`${rowAt(agent, "calls")}?status=broke`} />
          <Count label="Fixes ready" value={cases.groups === null ? "—" : String(fixes.length)} sub={fixes.length === 0 ? "nothing diagnosed waits" : "one click each"} to={rowAt(agent, "cases")} />
          <Count
            label="Goldens"
            value={cells === 0 ? "—" : `${held}/${cells}`}
            tone={cells === 0 ? undefined : held === cells ? "green" : "amber"}
            sub={cells === 0 ? "no run yet" : "held last run"}
            to={agent === "" ? undefined : `/a/${encodeURIComponent(agent)}/goldens`}
          />
        </div>
      </div>

      <Fixes groups={fixes} agent={agent} />

      <div className="qly-pair">
        <Rules rules={rules} picked={rule?.name ?? null} onPick={setPicked} agent={agent} />
        <BrokeIt rule={rule} scored={scored} cases={cases.listed?.cases ?? []} agent={agent} />
      </div>
    </Page>
  );
}
