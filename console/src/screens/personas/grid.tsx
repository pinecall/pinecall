/** The personas as cards in a grid: a face, who they are, how they act, how they have done — Pinecall's first, then the agent's own. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { ownedAt } from "../../lib/harness";
import { keepLibraryFolded, libraryFolded } from "../../lib/preferences";
import { Chips, Pill, Switch } from "../../ui";
import { isPinecalls, type Persona } from "./door";
import { Face } from "./face";
import { standingOf, type Standings } from "./use-run-standings";
import "./grid.css";

type Show = "all" | "realism" | "red-team" | "mine";

const SHOWS: readonly { value: Show; label: string }[] = [
  { value: "all", label: "All" },
  { value: "realism", label: "Realism" },
  { value: "red-team", label: "Red team" },
  { value: "mine", label: "Yours" },
];

const shown = (one: Persona, show: Show): boolean => (show === "all" ? true : show === "mine" ? !isPinecalls(one) : one.tags.includes(show));

export function PersonaGrid({
  agent,
  personas,
  standings,
  onSwitch,
}: {
  /** The agent in view, or "" for every agent: then each card names its agent. */
  agent: string;
  personas: Persona[];
  standings: Standings;
  /** One of Pinecall's switched on or off for its agent. */
  onSwitch: (persona: Persona, on: boolean) => void;
}): ReactNode {
  const [show, setShow] = useState<Show>("all");
  // Pinecall's library rests open, unless this person folded it: the browser keeps the choice. A
  // filter that names part of the library opens it whatever was kept.
  const [unfolded, setUnfolded] = useState(() => !libraryFolded());
  const fold = (): void => {
    keepLibraryFolded(unfolded);
    setUnfolded(!unfolded);
  };
  const these = personas.filter((one) => shown(one, show));
  // Realism first, the red team after: the order a person turns them on in.
  const library = these.filter(isPinecalls).sort((one, other) => Number(one.tags.includes("red-team")) - Number(other.tags.includes("red-team")) || one.name.localeCompare(other.name));
  const own = these.filter((one) => !isPinecalls(one));
  const draw = (one: Persona): ReactNode => <PersonaCard key={`${one.agent}/${one.name}`} agent={agent} persona={one} standings={standings} onSwitch={onSwitch} />;
  return (
    <section className="ui-tiles-block">
      <Chips options={SHOWS} value={show} onChange={setShow} />
      {own.length > 0 && (
        <>
          <h2 className="ui-tiles-title">
            {agent === "" ? "Written for your agents" : `Written for ${agent}`} <span>{own.length}</span>
          </h2>
          <div className="ui-tiles">{own.map(draw)}</div>
        </>
      )}
      {library.length > 0 && (
        <>
          <button type="button" className="psn-fold" aria-expanded={unfolded || show === "realism" || show === "red-team"} onClick={fold}>
            <span className="psn-fold-title">Pinecall's library</span>
            <span className="psn-fold-said">
              {agent === ""
                ? `${library.length} callers, realism and red team · switch them on with an agent in view`
                : `${library.length} callers ready to switch on — realism and red team · ${library.filter((one) => one.on).length} on`}
            </span>
            <span className="psn-fold-open">{unfolded || show === "realism" || show === "red-team" ? "Hide" : "Show them"}</span>
          </button>
          {(unfolded || show === "realism" || show === "red-team") && <div className="ui-tiles">{library.map(draw)}</div>}
        </>
      )}
      {these.length === 0 && <p className="ui-tiles-none">No persona matches.</p>}
    </section>
  );
}

function PersonaCard({ agent, persona, standings, onSwitch }: { agent: string; persona: Persona; standings: Standings; onSwitch: (persona: Persona, on: boolean) => void }): ReactNode {
  const library = isPinecalls(persona);
  const standing = standings.by[standingOf(persona)];
  const last = standing?.newest[0];
  const acts = [
    persona.behavior.interrupts > 0 ? `talks over ${Math.round(persona.behavior.interrupts * 100)}%` : null,
    persona.behavior.pause_s > 0 ? `pauses ${persona.behavior.pause_s}s` : null,
    persona.behavior.backchannels > 0 ? `murmurs ${Math.round(persona.behavior.backchannels * 100)}%` : null,
    persona.behavior.speed === 1 ? null : `${persona.behavior.speed}× tempo`,
    persona.behavior.interferer_db === null ? null : `from ${{ television: "a television", cafe: "a café", office: "an office", street: "a street" }[persona.behavior.ambience]}`,
  ].filter((one): one is string => one !== null);
  return (
    <article className={library && !persona.on ? "ui-tile ui-tile-off" : "ui-tile"}>
      <Link className="ui-tile-open" to={ownedAt(agent, "personas", persona.agent, persona.name)} aria-label={`Open ${persona.name}`} />
      <div className="ui-tile-top">
        <Face name={persona.name} size={64} />
        {library && agent === "" ? (
          <Pill tone="gray" small>
            Pinecall
          </Pill>
        ) : library ? (
          <Switch on={persona.on} label={`${persona.name} for ${persona.agent}`} onChange={(on) => onSwitch(persona, on)} />
        ) : (
          <Pill tone="violet" small>
            yours
          </Pill>
        )}
      </div>
      <h3 className="ui-tile-name">{persona.name}</h3>
      <p className="ui-tile-sub">{library ? (persona.summary ?? persona.goal) : persona.about !== "" ? persona.about : persona.goal}</p>
      <div className="ui-tile-tags">
        {agent === "" && !library && <Pill tone="gray" small>{persona.agent}</Pill>}
        {persona.tags.map((tag) => (
          <Pill key={tag} tone={tag === "red-team" ? "red" : "gray"} small>
            {tag}
          </Pill>
        ))}
      </div>
      <footer className="ui-tile-foot">
        <span>{acts.length === 0 ? "calm on the line" : acts.join(" · ")}</span>
        <span>
          {standings.read ? (standing === undefined || standing.total === 0 ? "never called" : last?.score == null ? `${standing.total} runs` : `${standing.total} runs · last ${last.score.passed ? "held" : "broke"}`) : ""}
        </span>
      </footer>
    </article>
  );
}
