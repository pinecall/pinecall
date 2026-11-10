/** One persona open: who it is and what it wants, only what it actually has beyond that, its calls, and the moves in the page's head. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { More } from "../apps/apps";
import { ConfirmButton } from "../apps/confirm";
import { AvatarOf, PersonaAvatar } from "../apps/avatar";
import { isPinecalls, standingOf, type Persona, type PersonaRun } from "../simulations/door";
import { Icon, type IconName } from "../shell/icons";
import { dropCaller } from "../test/door";
import { Select } from "../ui/select";
import { Badge } from "../ui/setting";
import { saidOf, tagsOf } from "./fold";
import { DOTS } from "./row";

function Part({ name, icon, children }: { name: string; icon: IconName; children: ReactNode }): ReactNode {
  return (
    <section className="dash-card ps-part" aria-label={name}>
      <h3 className="dash-eyebrow">
        <Icon name={icon} size={14} />
        {name}
      </h3>
      {children}
    </section>
  );
}

function Pairs({ rows }: { rows: readonly (readonly [string, string])[] }): ReactNode {
  return (
    <dl className="ps-pairs">
      {rows.map(([name, said]) => (
        <div key={name}>
          <dt>{name.replace(/_/g, " ")}</dt>
          <dd>{said}</dd>
        </div>
      ))}
    </dl>
  );
}

/** `agents` are the ones a simulation of one of Pinecall's may be run against when no agent is picked. */
export function PersonaActions({ persona, agent, agents, onEdit, onDropped }: { persona: Persona; agent: string; agents: readonly string[] | null; onEdit: () => void; onDropped: (callers: Persona[]) => void }): ReactNode {
  const credentials = useCredentials();
  const [against, setAgainst] = useState(agent);
  const [refused, setRefused] = useState<string | null>(null);
  const own = !isPinecalls(persona) && persona.fixed !== true;

  const drop = async (): Promise<void> => {
    setRefused(null);
    try {
      onDropped(await dropCaller(credentials, agent, persona.name));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <div className="app-actions">
      {refused !== null && <span className="app-refused">{refused}</span>}
      {agents !== null && agents.length > 1 && (
        <div className="ps-against">
          <Select label="Simulate against" value={against} items={agents.map((slug) => ({ value: slug, label: slug }))} onChange={setAgainst} />
        </div>
      )}
      {own && (
        <button type="button" className="app-button" onClick={onEdit}>
          Edit
        </button>
      )}
      <Link to={`/simulations?agent=${encodeURIComponent(against)}&persona=${encodeURIComponent(persona.name)}`} className="cfg-save ps-simulate">
        Simulate
      </Link>
      {own && (
        <More>
          <ConfirmButton label="Delete" asks="Delete for good?" danger onConfirm={() => void drop()} />
        </More>
      )}
    </div>
  );
}

export function PersonaView({ persona, agent, showsAgents, on, runs }: { persona: Persona; agent: string; showsAgents: boolean; on: boolean; runs: readonly PersonaRun[] }): ReactNode {
  const library = isPinecalls(persona);
  const facts = Object.entries(persona.facts);
  const who = library ? (persona.summary ?? "") : persona.about;
  const manner = tagsOf(persona.behavior);
  const runsOn = [
    ...(persona.llm === null ? [] : [["Model", persona.llm] as const]),
    ...(persona.voice === null && persona.tts === null ? [] : [["Voice", [persona.voice, persona.tts].filter((one) => one !== null).join(", on ")] as const]),
  ];

  return (
    <div className="ps-view">
      <section className="dash-card ps-hero" aria-label={persona.name}>
        <PersonaAvatar name={persona.name} size={68} />
        <div className="ps-hero-words">
          <h2 className="ps-name">{persona.name}</h2>
          {who !== "" && <p className="ps-who">{who}</p>}
          <div className="ps-marks">
            <Badge quiet>{library ? "Pinecall" : agent}</Badge>
            {on && <Badge>On for {agent}</Badge>}
            {persona.tags.includes("red-team") && <Badge quiet>Red team</Badge>}
            {persona.fixed === true && <Badge quiet>Set in its code</Badge>}
          </div>
        </div>
      </section>

      <div className="ps-parts">
        <Part name="Wants" icon="chat">
          <p className="ps-said">{persona.goal}</p>
        </Part>
        {(persona.style !== "" || manner.length > 0) && (
          <Part name="How they talk" icon="wave">
            {persona.style !== "" && <p className="ps-words">{persona.style}</p>}
            {manner.length > 0 && (
              <div className="ps-chips">
                {manner.map((one) => (
                  <span key={one} className="ps-chip">
                    {one}
                  </span>
                ))}
              </div>
            )}
          </Part>
        )}
        {persona.expects.length > 0 && (
          <Part name="Expects of the agent" icon="check">
            <ul className="ps-expects">
              {persona.expects.map((one) => (
                <li key={one}>
                  <span className="ps-tick" aria-hidden="true">
                    <Icon name="check" size={12} />
                  </span>
                  {one}
                </li>
              ))}
            </ul>
          </Part>
        )}
        {facts.length > 0 && (
          <Part name="What they know" icon="knowledge">
            <Pairs rows={facts} />
          </Part>
        )}
        {runsOn.length > 0 && (
          <Part name="Runs on" icon="settings">
            <Pairs rows={runsOn} />
          </Part>
        )}
        {runs.length > 0 && (
          <Part name="Simulated calls" icon="simulations">
            <div className="ps-calls">
              {runs.map((run) => (
                <Link key={run.call} to={`/simulations/${run.call}`} className="ps-call">
                  <span className={DOTS[standingOf(run)]} aria-hidden="true" />
                  <span className="ps-call-said dash-clip">{saidOf(run)}</span>
                  {showsAgents && (
                    <span className="dash-quiet ps-call-agent">
                      <AvatarOf name={run.agent} size={18} />
                      <span className="dash-clip">{run.agent}</span>
                    </span>
                  )}
                </Link>
              ))}
            </div>
          </Part>
        )}
      </div>
    </div>
  );
}
