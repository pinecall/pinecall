/** A call's own page, in the shell without the pane beside the call, drawn like every other page: what it came to, how it was judged, how fast and what it cost, the conversation, and what was under it. */

import type { ReactNode } from "react";
import { Link, useParams } from "react-router";

import { prettyNumber } from "@pinecall/core/calls";
import { medians } from "@pinecall/core/metrics";
import { useDeclaredState } from "../../lib/declared-state";
import { dayAndTime, duration, usd, visitorOf } from "../../lib/format";
import { useWayBack } from "../../lib/whence";
import { Card, CardHead, Page, PageHead, Pill, Stat, Stats } from "../../ui";
import { ChatView } from "./chat-view";
import { MetricsPanel } from "./metrics-panel";
import { CostCard, LatencyCard, Outcome, ScoreCard, scoreIn, TimeCard, timeSpentIn } from "./over";
import { PromptPanel } from "./prompt-panel";
import { RoomPanel } from "./room-panel";
import { StatePanel } from "./state-panel";
import { TraceIdPanel } from "./trace-id";
import { useWatchedCall } from "./use-watched-call";
import "./show.css";

/** `calls/:call/show`: one call read at leisure. */
export function CallShow(): ReactNode {
  const call = useParams()["call"] ?? "";
  const back = useWayBack(`/calls/${encodeURIComponent(call)}`);
  const watched = useWatchedCall(call);
  const state = watched.state;
  const declared = useDeclaredState(state.agent);
  const over = state.status === "ended";
  const latencies = medians(watched.entries);
  const score = scoreIn(watched.entries);
  const spent = timeSpentIn(watched.entries, state);
  const address = state.direction === "outbound" ? state.to : state.from;
  const who = state.caller?.name ?? visitorOf(address) ?? (address === null ? "A caller" : address.startsWith("+") ? prettyNumber(address) : address);
  const held = score?.judges.filter((judge) => judge.verdict === "held").length ?? 0;
  const settled = score?.judges.filter((judge) => judge.verdict === "held" || judge.verdict === "broken").length ?? 0;
  // The caller's wait for the reply, or nothing: another measure under this label would be a wrong number.
  const response = latencies.find((row) => row.name === "e2e_latency");

  return (
    <Page width={1060}>
      <PageHead
        title={who}
        back={<Link to={back.to}>← {back.name}</Link>}
        lede={[state.agent, state.channel, state.direction === "outbound" ? "outbound" : "inbound", dayAndTime(state.started_at)].filter(Boolean).join(" · ")}
        actions={over ? <Pill tone="gray">{(state.end_reason ?? "ended").replace(/_/g, " ")}</Pill> : <Pill tone="green">{state.status}</Pill>}
      />

      <Outcome state={state} />

      <Stats min={150}>
        <Stat size="small" label="Duration" value={state.ended_at === null ? "still going" : duration(state)} />
        <Stat size="small" label="Turns" value={state.turns.length} />
        <Stat size="small" label="Response" value={response === undefined ? "—" : `${response.seconds.toFixed(2)} s`} of={response === undefined ? undefined : "median wait for a reply"} />
        <Stat size="small" label="Cost" value={usd(state.cost?.usd)} />
        <Stat
          size="small"
          label="Judges"
          value={score === null ? "not scored" : settled === 0 ? "no verdict" : `${held} of ${settled} held`}
          tone={score === null || settled === 0 ? undefined : score.passed ? "green" : "red"}
        />
      </Stats>

      <ScoreCard call={call} base="/calls" score={score} turns={state.turns.length} ended={over} />
      <LatencyCard rows={latencies} />
      {spent !== null && <TimeCard spent={spent} />}
      {state.cost !== null && state.cost.rows.length > 0 && <CostCard cost={state.cost} />}

      <Card>
        <CardHead title="Conversation" meta={`${state.turns.length} turns`} />
        <div className="show-conversation">
          <ChatView entries={watched.entries} state={state} />
        </div>
      </Card>

      <Card>
        <div className="show-panel">
          <StatePanel fields={state.app_state} declared={declared} />
        </div>
      </Card>
      <Card>
        <div className="show-panel">
          <RoomPanel room={state.room} from={state.from} over={over} />
        </div>
      </Card>
      <Card>
        <div className="show-panel">
          <PromptPanel prompt={state.prompt} cost={state.cost} />
        </div>
      </Card>
      <Card>
        <div className="show-panel">
          <MetricsPanel metrics={state.metrics} entries={watched.entries} />
        </div>
      </Card>
      <TraceIdPanel call={call} />
    </Page>
  );
}
