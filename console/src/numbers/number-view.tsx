/** One number open: who answers it and where it comes through, what a call to it goes through now, and what can be done to it. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { ago } from "../lib/format";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Select } from "../ui/select";
import { addNumber, moveNumber, releaseNumber, type Carrier, type Catalog, type NumberRow, type Wired } from "./door";
import { Path, Plan, useMove } from "./parts";
import { comesThrough, RINGS, shown } from "./words";

const OTHER = WORLD === "production" ? "sandbox" : "production";

/** Where an agent's own page is: Agents for one built in Studio, Apps for one written as code. */
export function useAgentPage(): (agent: string, tab?: string) => string {
  const { agents } = useOrg();
  return (agent, tab = "") => `/${agents.find((one) => one.slug === agent)?.kind === "studio" ? "agents" : "apps"}/${encodeURIComponent(agent)}${tab === "" ? "" : `/${tab}`}`;
}

function Fact({ name, children }: { name: string; children: ReactNode }): ReactNode {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function NumberView({ row, carriers, catalog, agents, onChanged, onGone }: { row: NumberRow; carriers: readonly Carrier[]; catalog: Catalog | null; agents: readonly string[]; onChanged: () => void; onGone: () => void }): ReactNode {
  const credentials = useCredentials();
  const mover = useMove();
  const pageOf = useAgentPage();
  const number = row.route.number ?? "";
  const [round, setRound] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [plan, setPlan] = useState<Wired | null>(null);
  const rings = RINGS[row.rings];
  // A number is sent to another agent the way it was added; only one imported from an account says enough here to do it again.
  const movable = row.origin === "imported" && row.account != null && row.route.channel !== "web";
  const wanted = (agent: string) => ({ number, agent, channel: row.route.channel as "phone" | "whatsapp", ...(row.account == null ? {} : { account: row.account }) });
  const done = (): void => {
    setPlan(null);
    setNext(null);
    setRound((was) => was + 1);
    onChanged();
  };

  return (
    <div className="num-open">
      <section className="dash-card num-card">
        <div className="num-card-top">
          <span className="num-big">{shown(row.route.number)}</span>
          <span className={`num-rings num-rings-${rings.mood}`}>{rings.said}</span>
        </div>
        <dl className="num-facts">
          <Fact name="Answered by">
            <Link to={pageOf(row.route.agent, "channels")} className="num-agent">
              {row.route.agent}
            </Link>
          </Fact>
          <Fact name="Channel">{row.route.channel === "whatsapp" ? "WhatsApp" : "Phone"}</Fact>
          <Fact name="Comes through">{comesThrough(row, carriers, catalog)}</Fact>
          <Fact name="Last call">{row.last_call_at == null ? "None yet" : ago(row.last_call_at)}</Fact>
        </dl>
      </section>

      <section className="dash-card num-card">
        <span className="dash-eyebrow dash-eyebrow-head">What a call to it goes through</span>
        <Path number={number} round={round} />
      </section>

      <section className="dash-card num-card">
        <span className="dash-eyebrow dash-eyebrow-head">Change it</span>
        {mover.refused !== null && (
          <p className="cfg-refused" role="alert">
            {mover.refused}
          </p>
        )}
        {plan !== null && next !== null ? (
          <Plan plan={plan} busy={mover.busy} confirm={`Send it to ${next}`} onBack={() => setPlan(null)} onConfirm={() => void mover.move(() => addNumber(credentials, wanted(next), false)).then(done, () => undefined)} />
        ) : (
          <div className="num-changes">
            <div className="num-change">
              <span className="num-change-words">
                <span className="num-change-title">Another agent answers</span>
                <span className="dash-quiet">{movable ? "Pick the agent, then read what will change before it does." : "This number was not imported from one of your accounts: add it again for the other agent."}</span>
              </span>
              {movable && <Select label="Agent that picks up" items={agents.map((one) => ({ value: one, label: one }))} value={row.route.agent} disabled={mover.busy} onChange={(agent) => agent !== row.route.agent && void mover.move(() => addNumber(credentials, wanted(agent), true)).then((read) => (setNext(agent), setPlan(read)), () => undefined)} />}
            </div>
            <div className="num-change">
              <span className="num-change-words">
                <span className="num-change-title">Move it to {OTHER}</span>
                <span className="dash-quiet">{OTHER === "production" ? "Calls to it reach the agent as it is deployed, and count as real calls." : "Calls to it reach the agent as you are building it."}</span>
              </span>
              <ConfirmButton label={`Move to ${OTHER}`} asks={`Move it to ${OTHER}?`} onConfirm={() => void mover.move(() => moveNumber(credentials, number, OTHER)).then(onGone, () => undefined)} />
            </div>
            <div className="num-change">
              <span className="num-change-words">
                <span className="num-change-title">Let it go</span>
                <span className="dash-quiet">It stops reaching Pinecall. The account that owns it keeps it.</span>
              </span>
              <ConfirmButton label="Let it go" asks="Stop answering it?" danger onConfirm={() => void mover.move(() => releaseNumber(credentials, number)).then(onGone, () => undefined)} />
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
