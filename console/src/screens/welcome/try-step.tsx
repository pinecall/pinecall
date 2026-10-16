/** Step: a written chat with the agent, here on the page, through the same room the Chat screen opens. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import { Refused, Select, SelectItem } from "../../ui";
import { Composer, Conversation } from "../talk/lines";
import { useRoom } from "../talk/use-room";
import { NotRunning } from "./not-running";
import { SLUG } from "./agent-code";
import "../talk/talk.css";

export function TryStep({ agents, onBack }: { agents: HeldAgent[]; onBack: () => void }): ReactNode {
  const [picked, setPicked] = useState("");
  // The agent the guide had written is the one to talk to, when it is up; else whichever the person picks.
  const agent = agents.find((one) => one.slug === picked)?.slug ?? agents.find((one) => one.slug === SLUG)?.slug ?? agents[0]?.slug ?? null;
  return (
    <>
      <p className="wel-lead">
        {agent === null
          ? "Once your agent is running, this is where you talk to it in writing, before any phone rings: it costs no minutes, and every tool it calls shows in the conversation."
          : "Talk to it in writing, before any phone rings. It costs no minutes, and every tool it calls shows in the conversation."}
      </p>
      {agent === null ? <NotRunning doing="A chat" onBack={onBack} /> : <Chat agent={agent} agents={agents} onPick={setPicked} />}
    </>
  );
}

function Chat({ agent, agents, onPick }: { agent: string; agents: HeldAgent[]; onPick: (slug: string) => void }): ReactNode {
  const live = useRoom(agent);
  const inside = live.phase === "live" || live.phase === "connecting";
  const write = async (text: string): Promise<void> => (inside ? live.write(text) : live.open("chat", text));
  return (
    <div className={live.lines.length > 0 ? "wel-chat wel-chat-live" : "wel-chat"}>
      <div className="wel-chat-head">
        {agents.length > 1 ? (
          <Select size="sm" value={agent} onValueChange={onPick} aria-label="Which agent">
            {agents.map((one) => (
              <SelectItem key={one.slug} value={one.slug}>
                {one.slug}
              </SelectItem>
            ))}
          </Select>
        ) : (
          <strong>{agent}</strong>
        )}
        <span className="wel-hint">{live.phase === "idle" ? "Write below to start." : live.phase === "connecting" ? "Joining…" : live.phase === "live" ? "Talking" : live.phase === "ended" ? "Ended. Write to start another." : "Could not join."}</span>
        {live.call !== null && (
          <Link className="wel-go" to={`/calls/${encodeURIComponent(live.call)}/show`}>
            Open the call's page
          </Link>
        )}
      </div>
      <div className="wel-chat-body">
        {live.lines.length === 0 ? <div className="wel-chat-empty">Say hello, or ask what the business does: the agent answers as it would a caller.</div> : <Conversation lines={live.lines} />}
      </div>
      <Refused>{live.error}</Refused>
      <Composer placeholder={`Message ${agent}…`} disabled={live.phase === "connecting"} onWrite={write} />
    </div>
  );
}
