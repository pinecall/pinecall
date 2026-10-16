/** Pipeline screen: providers, turn latency breakdown and hold audio. */

import type { ReactNode } from "react";

import { Link, useParams } from "react-router";

import { Card, Empty, Page, PageHead } from "../../ui";
import { HoldMelody } from "./hold";
import { DecidesLeg, HearsLeg, SpeaksLeg } from "./legs";
import { usePipeline } from "./use-pipeline";
import { Waterfall } from "./waterfall";
import "./pipeline.css";

export function Pipeline(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const { report, error } = usePipeline(agent);

  return (
    <Page tight>
      <PageHead
        title="Pipeline"
        ledeWidth={660}
        lede="The three legs of a voice turn as data, not prose: what hears, what decides, what speaks — every value read from the gateway with this agent's settings already laid over the class."
      />

      {report === null ? (
        <Card>
          <Empty>{error ?? `Asking the gateway what ${agent} runs on…`}</Empty>
        </Card>
      ) : (
        <>
          <div className="pipe-legs">
            <HearsLeg stage={report.hears} unavailable={report.unavailable_reasons["hears"] ?? null} />
            <DecidesLeg stage={report.decides} unavailable={report.unavailable_reasons["decides"] ?? null} />
            <SpeaksLeg stage={report.speaks} unavailable={report.unavailable_reasons["speaks"] ?? null} />
          </div>

          <Waterfall medians={report.medians} calls={report.calls} agent={agent} />

          <Card>
            <Empty>
              Changing any of it is the <Link to={`/a/${encodeURIComponent(agent)}/configure`}>Configure</Link> tab: the vendors and models with the opening, the cut of a turn and what is remembered, per corner and versioned.
            </Empty>
          </Card>
          <HoldMelody key={`hold-${agent}`} agent={agent} />
        </>
      )}
    </Page>
  );
}
