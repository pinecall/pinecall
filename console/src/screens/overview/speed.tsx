/** How fast the agent in view answers: the median of each measure of a turn over its newest calls, off its pipeline report. */

import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { seconds } from "@pinecall/core/metrics";
import { percent } from "../../lib/format";
import { Card, CardHead, Empty } from "../../ui";
import { LATENCY_NAMES } from "../call";
import { readPipeline, type Report } from "../pipeline/door";

/** The report: undefined while asked, null when the door refused — and what it refused with. */
function usePipeline(agent: string): { report: Report | null | undefined; refused: string | null } {
  const credentials = useCredentials();
  const [report, setReport] = useState<Report | null | undefined>(undefined);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    let gone = false;
    readPipeline(credentials, agent).then(
      (read) => {
        if (!gone) setReport(read);
      },
      (failed: unknown) => {
        if (gone) return;
        setReport(null);
        setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);
  return { report, refused };
}

export function Speed({ agent }: { agent: string }): ReactNode {
  const { report, refused } = usePipeline(agent);
  return (
    <Card>
      <CardHead title="How fast it answers" meta={report === undefined ? "reading…" : report === null ? undefined : `median over ${report.calls} calls`} />
      {report === undefined ? null : report === null ? (
        <Empty>{refused}</Empty>
      ) : report.medians.length === 0 ? (
        <Empty>No turn has been measured yet.</Empty>
      ) : (
        <div className="ovw-speed">
          {report.medians.map((one) => (
            <div key={one.name} className="ovw-speed-one">
              <span className="ovw-speed-value">{one.name === "talk_share" ? percent(one.seconds) : seconds(one.seconds)}</span>
              <span className="ovw-speed-name">{LATENCY_NAMES[one.name] ?? one.name}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
