/** A check call, production's own form: one pretend caller rings the agent as it is deployed, once. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { money } from "../lib/format";
import { inWorld } from "../lib/world";
import { Select } from "../ui/select";
import type { Rung, Typical } from "./composer";
import { aboutOf, inOrder, isPinecalls, readCallers, startSimulation, type Persona } from "./door";
import { askedBy, HowTheyCall, USUAL_HOW, type How } from "./how";

export function CheckCall({ agents, asked, askedCaller = null, typical, onStarted }: { agents: readonly Rung[]; asked: string | null; askedCaller?: string | null; typical: Typical; onStarted: (calls: string[]) => void }): ReactNode {
  const credentials = useCredentials();
  const [agent, setAgent] = useState(asked !== null && agents.some((one) => one.slug === asked) ? asked : (agents[0]?.slug ?? ""));
  const [callers, setCallers] = useState<Persona[] | null>(null);
  const [caller, setCaller] = useState("");
  const [how, setHow] = useState<How>(USUAL_HOW);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  // The agents are read after the page is drawn: the first one is taken once they are.
  useEffect(() => {
    if (agent === "" && agents[0] !== undefined) setAgent(agents[0].slug);
  }, [agent, agents]);

  // Another agent has other callers: the one chosen for the last is not carried over.
  useEffect(() => {
    if (agent === "") return;
    let gone = false;
    setCallers(null);
    setCaller("");
    setRefused(null);
    readCallers(credentials, agent).then(
      (read) => {
        if (gone) return;
        setCallers(read);
        if (askedCaller !== null && agent === asked && read.some((one) => one.name === askedCaller)) setCaller(askedCaller);
      },
      (failed) => {
        if (gone) return;
        setCallers([]);
        setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const run = async (): Promise<void> => {
    if (starting || caller === "") return;
    setStarting(true);
    setRefused(null);
    try {
      onStarted([await startSimulation(credentials, { agent, persona: caller, ...askedBy(how) })]);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setStarting(false);
    }
  };

  if (agents.length === 0) {
    return (
      <div className="app-open-note">
        <div className="app-empty">
          <h2 className="app-name">No agent is deployed</h2>
          <p className="dash-quiet">A check call rings an agent that is running in production. Deploy one and it shows up here.</p>
          <code className="app-command">pinecall deploy</code>
        </div>
      </div>
    );
  }

  const offered = inOrder(callers ?? []).filter((one) => !isPinecalls(one) || one.on);
  const minutes = typical.seconds === null ? null : Math.max(1, Math.round(typical.seconds / 60));
  const foot = [caller === "" ? "Pick the caller" : "1 call", caller !== "" && minutes !== null ? `about ${minutes} min` : null, caller !== "" && typical.usd !== null ? `around ${money(typical.usd)}` : null, caller !== "" ? "judged at hang-up" : null].filter((part) => part !== null);

  return (
    <div className="app-main">
      <header className="sim-check-head">
        <h2 className="app-name">Check call</h2>
        <p className="dash-quiet">One pretend caller rings the agent as it is deployed, on production's own keys and knowledge, and the call is judged when it ends.</p>
      </header>

      <section className="dash-card" aria-label="Who rings whom">
        <div className="sim-check-fields">
          <label className="sim-check-field">
            <span className="dash-eyebrow">Agent</span>
            <Select label="The agent to check" value={agent} items={agents.map((one) => ({ value: one.slug, label: one.slug }))} onChange={setAgent} />
          </label>
          <label className="sim-check-field">
            <span className="dash-eyebrow">Caller</span>
            <Select label="Who calls" value={caller} placeholder={callers === null ? "Reading the callers…" : "Choose a caller"} disabled={callers === null || offered.length === 0} items={offered.map((one) => ({ value: one.name, label: one.name, detail: aboutOf(one) }))} onChange={setCaller} />
          </label>
        </div>
        {callers !== null && offered.length === 0 && refused === null && <p className="dash-quiet sim-check-none">This agent has no caller yet. Write the first one in its Test tab.</p>}
      </section>

      <HowTheyCall title="How it calls" how={how} onChange={setHow} />

      {refused !== null && <p className="app-refused">{refused}</p>}
      <footer className="sim-foot">
        <span className="dash-quiet">{foot.join(" · ")}</span>
        <button type="button" className="sim-run" disabled={starting || caller === ""} onClick={() => void run()}>
          {starting ? "Starting…" : "Run check"}
        </button>
      </footer>
      <p className="dash-quiet sim-check-more">
        Several callers at once, and the same tasks on other models, ears and voices, run in the sandbox:{" "}
        <a className="sim-link" href={inWorld("sandbox", "/simulations")}>
          open Simulations there
        </a>
        .
      </p>
    </div>
  );
}
