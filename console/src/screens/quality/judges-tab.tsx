/** Judges, a tab of Test: the model the org's calls are judged on, every judge a call meets at hang-up, how each has held, and the form a new one is written in. */

import { useMemo, type ReactNode } from "react";
import { useParams } from "react-router";

import { useOrg } from "../../lib/org";
import { useScores } from "../../lib/use-scores";
import { Page, PageHead } from "../../ui";
import { useDrift } from "./drift";
import { JudgeModel } from "./judge-model";
import { Judges } from "./judges";
import { heldRates } from "./held-rates";
import "./quality.css";

/** The held-rates are folded from the newest verdicts the page read; the drift is the process holding the agent's count. */
export function JudgesTab(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const { lines } = useOrg();
  const mine = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const scored = useScores(mine);
  const verdicts = scored.flatMap((row) => (row.score === null ? [] : [row.score]));
  const rates = heldRates(verdicts);
  const drifted = useDrift(agent);

  return (
    <Page tight>
      <PageHead
        title="Judges"
        lede="One question each, asked of every call at hang-up. A judge that breaks opens a case."
      />
      {agent === "" && <JudgeModel />}
      <Judges agent={agent} rates={rates} read={verdicts.length} drifted={drifted} />
    </Page>
  );
}
