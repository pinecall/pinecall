/** The pane's account of one bar of the trace: the block, the tool or the turn behind it, field by field. */

import type { ReactNode } from "react";

import { blockShapes, headline, readings, seconds } from "@pinecall/core/metrics";
import { SectionLabel, TextAction } from "../../ui";
import { Readings } from "./readings";
import { toolReadings } from "./tool-run";
import { type Behind, type TraceBar } from "./trace-bars";

export function TraceStep({ bar, onClose }: { bar: TraceBar; onClose: () => void }): ReactNode {
  const length = bar.to - bar.from;
  return (
    <>
      <SectionLabel ruled>
        Step <TextAction onClick={onClose}>close</TextAction>
      </SectionLabel>
      <div className="call-pane-body">
        <div className="trace-step-head">
          <span className="trace-step-name">{bar.label}</span>
          <span className="trace-step-when">
            at {bar.from.toFixed(2)} s{length > 0 && ` · ${seconds(length)}`}
            {bar.cut && (bar.kind === "tool" ? " · failed" : bar.kind === "agent" ? " · interrupted" : " · cancelled")}
          </span>
        </div>
        <What behind={bar.behind} />
      </div>
    </>
  );
}

function What({ behind }: { behind: Behind }): ReactNode {
  switch (behind.kind) {
    case "block":
      return <Readings rows={readings(behind.at, blockShapes().get(behind.block))} />;
    case "tool":
      return <Readings rows={toolReadings(behind.run)} />;
    case "turn":
      return (
        <>
          <p className="trace-step-said">{behind.turn.text}</p>
          <Readings rows={headline(behind.turn)} />
        </>
      );
  }
}
