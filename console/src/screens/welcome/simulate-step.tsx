/** Step: a simulated caller plays a whole conversation against the agent, started here and watched as it happens. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import { Button, Refused } from "../../ui";
import { ChatView } from "../call/chat-view";
import { useWatchedCall } from "../call/use-watched-call";
import { startSimulation } from "../simulations/simulating";
import { Command } from "./command";
import { NotRunning } from "./not-running";
import { SLUG } from "./agent-code";
import "../call/call.css";

// One of Pinecall's own callers, there for every agent: two minutes, wants it done.
const PERSONA = "in-a-hurry";
const TURNS = 6;

export function SimulateStep({ agents, onBack }: { agents: HeldAgent[]; onBack: () => void }): ReactNode {
  const credentials = useCredentials();
  const agent = agents.find((one) => one.slug === SLUG)?.slug ?? agents[0]?.slug ?? null;
  const [call, setCall] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const start = async (): Promise<void> => {
    if (agent === null) return;
    setBusy(true);
    setRefused(null);
    try {
      setCall(await startSimulation(credentials, { agent, persona: PERSONA, voice: false, turns: TURNS }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <p className="wel-lead">
        A model plays a caller, in a hurry, for a few turns against your agent. Written, so it costs no minutes. This is how you test an agent without calling it yourself a hundred
        times: Pinecall ships a dozen such callers, and you write your own.
      </p>
      {agent === null ? (
        <NotRunning doing="A simulation" onBack={onBack} />
      ) : call === null ? (
        <div className="wel-block">
          <strong>Caller: in a hurry</strong>
          <span className="wel-hint">Short sentences, interrupts a long answer, loses patience after two questions in a row. {TURNS} turns, then it hangs up.</span>
          <div>
            <Button kind="primary" size="md" disabled={busy} onClick={() => void start()}>
              {busy ? "Starting…" : `Run it against ${agent}`}
            </Button>
          </div>
          <Refused>{refused}</Refused>
        </div>
      ) : (
        <Watched call={call} onAgain={() => setCall(null)} />
      )}
      <span className="wel-hint">The same, from the terminal, with the judges scoring it at the end:</span>
      <Command line={`pinecall simulate --persona ${PERSONA} --judge`} say="from the agent's folder" />
    </>
  );
}

function Watched({ call, onAgain }: { call: string; onAgain: () => void }): ReactNode {
  const watched = useWatchedCall(call);
  const over = watched.state.status === "ended";
  return (
    <div className="wel-chat">
      <div className="wel-chat-head">
        <strong>{over ? "The call ended" : "On the line"}</strong>
        <span className="wel-hint">{over ? "Every turn and tool call is on its page." : "The caller and your agent, as they speak."}</span>
        <Link className="wel-go" to={`/calls/${encodeURIComponent(call)}/show`}>
          Open the call's page
        </Link>
        {over && (
          <Button size="xs" onClick={onAgain}>
            Run another
          </Button>
        )}
      </div>
      <div className="wel-chat-body">
        <ChatView entries={watched.entries} state={watched.state} />
      </div>
      <Refused>{watched.error}</Refused>
    </div>
  );
}
