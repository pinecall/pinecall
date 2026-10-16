/** Where a finished call's time went, on a card: one bar cut into its parts, then each part in seconds and share. */

import type { ReactNode } from "react";

import { seconds } from "@pinecall/core/metrics";
import { percent } from "../../../lib/format";
import { Card, CardHead } from "../../../ui";
import { type Spent, type TimeSpent } from "./time-spent";

// What a person calls each kind, and what it means, in the hover.
const SAID: Record<Spent, { name: string; means: string }> = {
  before: { name: "Before the first word", means: "From the call's start until anybody spoke" },
  caller: { name: "Caller speaking", means: "The caller alone" },
  agent: { name: "Agent speaking", means: "The agent alone" },
  both: { name: "Both at once", means: "Talking over each other: an interruption, or a word of agreement" },
  on_the_agent: { name: "Waiting on the agent", means: "Silence after the caller spoke, while no tool ran" },
  tool: { name: "Waiting on a tool", means: "Silence while a tool ran" },
  on_the_caller: { name: "Waiting on the caller", means: "Silence after the agent spoke" },
  person: { name: "With a person", means: "After a transfer, or while a supervisor held the line: the agent was out of it" },
};

export function TimeCard({ spent }: { spent: TimeSpent }): ReactNode {
  return (
    <Card>
      <CardHead title="Where the time went" meta={seconds(spent.length)} />
      <div className="over-spent">
        <div className="over-spent-bar" role="img" aria-label="the call's time, part by part">
          {spent.parts.map((part) => (
            <span key={part.kind} className={`over-spent-part over-spent-${part.kind}`} style={{ flexGrow: part.seconds }} title={SAID[part.kind].name} />
          ))}
        </div>
        {spent.parts.map((part) => (
          <div key={part.kind} className="over-spent-row" title={SAID[part.kind].means}>
            <span className={`over-spent-swatch over-spent-${part.kind}`} aria-hidden />
            <span className="over-spent-name">{SAID[part.kind].name}</span>
            <span className="over-spent-seconds">{seconds(part.seconds)}</span>
            <span className="over-spent-share">{percent(part.seconds / spent.length)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
