/** The personas as a roster: one row each — who they are, what kind of caller, how they act on the line, how they have done — the agent's own first, then Pinecall's library. */

import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { ownedAt } from "../../lib/harness";
import { keepLibraryFolded, libraryFolded } from "../../lib/preferences";
import { Avatar, Card, CardHead, Chips, Pill, Switch, TableHead, TableRow, TextAction } from "../../ui";
import { isPinecalls, type Persona } from "./door";
import { standingOf, type Standings } from "./use-run-standings";
import "./grid.css";

type Show = "all" | "realism" | "red-team" | "mine";

const SHOWS: readonly { value: Show; label: string }[] = [
  { value: "all", label: "All" },
  { value: "realism", label: "Realism" },
  { value: "red-team", label: "Red team" },
  { value: "mine", label: "Yours" },
];

const COLUMNS = "minmax(0, 2.6fr) 110px minmax(0, 1.2fr) 150px 64px";

const shown = (one: Persona, show: Show): boolean => (show === "all" ? true : show === "mine" ? !isPinecalls(one) : one.tags.includes(show));

export function PersonaGrid({
  agent,
  personas,
  standings,
  onSwitch,
}: {
  /** The agent in view, or "" for every agent: then each row names its agent. */
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
  const open = unfolded || show === "realism" || show === "red-team";
  const rows = (list: Persona[]): ReactNode => (
    <>
      <TableHead columns={COLUMNS} labels={["Persona", "Kind", "On the line", "Runs", ""]} />
      {list.map((one) => (
        <Row key={`${one.agent}/${one.name}`} agent={agent} persona={one} standings={standings} onSwitch={onSwitch} />
      ))}
    </>
  );
  return (
    <section className="psn-roster">
      <Chips options={SHOWS} value={show} onChange={setShow} />
      {own.length > 0 && (
        <Card>
          <CardHead title={agent === "" ? "Written for your agents" : `Written for ${agent}`} meta={`${own.length}`} />
          {rows(own)}
        </Card>
      )}
      {library.length > 0 && (
        <Card>
          <CardHead
            title="Pinecall's library"
            meta={agent === "" ? `${library.length} callers · switch them on with an agent in view` : `${library.length} callers · ${library.filter((one) => one.on).length} on for ${agent}`}
            action={<TextAction onClick={fold}>{open ? "Hide" : "Show"}</TextAction>}
          />
          {open && rows(library)}
        </Card>
      )}
      {these.length === 0 && <p className="psn-none">No persona matches.</p>}
    </section>
  );
}

// How the caller acts on the line, in a few words; nothing said is a calm caller.
function actsOf(persona: Persona): string {
  const { behavior } = persona;
  const acts = [
    behavior.interrupts > 0 ? `talks over ${Math.round(behavior.interrupts * 100)}%` : null,
    behavior.pause_s > 0 ? `pauses ${behavior.pause_s}s` : null,
    behavior.backchannels > 0 ? `murmurs ${Math.round(behavior.backchannels * 100)}%` : null,
    behavior.speed === 1 ? null : `${behavior.speed}× tempo`,
    behavior.interferer_db === null ? null : `from ${{ television: "a television", cafe: "a café", office: "an office", street: "a street" }[behavior.ambience]}`,
  ].filter((one): one is string => one !== null);
  return acts.length === 0 ? "Calm" : acts.join(" · ");
}

function Row({ agent, persona, standings, onSwitch }: { agent: string; persona: Persona; standings: Standings; onSwitch: (persona: Persona, on: boolean) => void }): ReactNode {
  const navigate = useNavigate();
  const library = isPinecalls(persona);
  const standing = standings.by[standingOf(persona)];
  const last = standing?.newest[0];
  const said = library ? (persona.summary ?? persona.goal) : persona.about !== "" ? persona.about : persona.goal;
  const red = persona.tags.includes("red-team");
  return (
    <TableRow columns={COLUMNS} onClick={() => void navigate(ownedAt(agent, "personas", persona.agent, persona.name))}>
      <span className={library && !persona.on ? "psn-who psn-who-off" : "psn-who"}>
        <Avatar name={persona.name} size={36} round />
        <span className="psn-who-words">
          <span className="psn-who-name">
            {persona.name}
            {agent === "" && !library && <span className="psn-who-agent">{persona.agent}</span>}
          </span>
          <span className="psn-who-said">{said}</span>
        </span>
      </span>
      <span>
        <Pill tone={red ? "red" : library ? "gray" : "violet"} small>
          {red ? "Red team" : library ? "Realism" : persona.owner === "class" ? "The class's" : "Custom"}
        </Pill>
      </span>
      <span className="psn-quiet">{actsOf(persona)}</span>
      <span className="psn-quiet">
        {!standings.read ? "" : standing === undefined || standing.total === 0 ? "Never run" : last?.score == null ? `${standing.total} runs` : (
          <>
            {standing.total} runs · <span className={last.score.passed ? "psn-held" : "psn-broke"}>last {last.score.passed ? "held" : "broke"}</span>
          </>
        )}
      </span>
      {/* A switch inside a row that opens the persona: the click is the switch's alone. */}
      <span className="psn-switch" onClick={(event) => event.stopPropagation()}>
        {library && agent !== "" && persona.fixed !== true && <Switch on={persona.on} label={`${persona.name} for ${persona.agent}`} onChange={(on) => onSwitch(persona, on)} />}
        {library && persona.fixed === true && <span className="psn-quiet">{persona.on ? "on" : "off"} · the class's</span>}
      </span>
    </TableRow>
  );
}
