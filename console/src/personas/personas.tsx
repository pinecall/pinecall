/** Personas, the same page as Agents and Simulations: every caller a model plays in a list, yours and Pinecall's, beside the one open. */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Navigate, useSearchParams } from "react-router";

import { useOrg } from "../lib/org";
import { PageHead } from "../shell/page-head";
import { isPinecalls, type Persona } from "../simulations/door";
import { CallerFormPanel, ProposePanel } from "../test/caller-panel";
import { setInCode } from "../test/fold";
import { AgentPick } from "../ui/agent-pick";
import { AskAgent } from "./ask-agent";
import { callsOf, libraryOf, matches, newestCallsOf, ownOf } from "./fold";
import { PersonaActions, PersonaView } from "./persona";
import { Row } from "./row";
import { useRosters } from "./use-rosters";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../calls/calls.css";
import "../configure/configure.css";
import "../test/test.css";
import "./personas.css";

const HOME = "/personas";
const AGENT = "agent";
const PERSONA = "persona";
// Whose list the open persona is read from; absent for one of Pinecall's while every agent is shown.
const OF = "of";

/** The panel that writes: the form on a persona or a new one, the callers a model proposes, or the question of which agent. */
type Writing = { kind: "form"; agent: string; was: Persona | undefined; among?: readonly string[] } | { kind: "generate"; agent: string } | { kind: "ask" };

function Personas({ agent, open, go }: { agent: string; open: { name: string; of: string } | null; go: (changes: Record<string, string>) => void }): ReactNode {
  const { agents, agentsRead } = useOrg();
  const slugs = useMemo(() => (agent !== "" ? [agent] : agents.map((one) => one.slug).sort()), [agent, agents]);
  const { rosters, setCallers } = useRosters(slugs);
  const [search, setSearch] = useState("");
  const [writing, setWriting] = useState<Writing | null>(null);
  const close = useCallback(() => go({ [PERSONA]: "", [OF]: "" }), [go]);
  const shut = useCallback(() => setWriting(null), []);

  const callersOf = (slug: string): Persona[] => rosters.get(slug)?.callers ?? [];
  // Pinecall's personas are read through an agent: the first that answered stands for all while every agent is shown.
  const source = slugs.find((slug) => (rosters.get(slug)?.callers ?? null) !== null);
  const library = source === undefined ? [] : libraryOf(callersOf(source));
  const shelf = agent === "" ? "" : agent;
  const writable = slugs.filter((slug) => !setInCode(callersOf(slug)));

  const start = (then: "form" | "generate"): void => {
    const only = agent !== "" ? agent : writable.length === 1 ? writable[0] : undefined;
    // A new persona asks whose it is in its own form; a model has to be told the agent before it writes any.
    if (then === "form") {
      const first = only ?? writable[0];
      if (first !== undefined) setWriting({ kind: "form", agent: first, was: undefined, ...(only === undefined ? { among: writable } : {}) });
    } else if (only === undefined) setWriting({ kind: "ask" });
    else setWriting({ kind: "generate", agent: only });
  };

  const addressOf = (of: string, name: string): string => {
    const next = new URLSearchParams();
    if (agent !== "") next.set(AGENT, agent);
    next.set(PERSONA, name);
    if (of !== "") next.set(OF, of);
    return `?${next.toString()}`;
  };
  const isOpen = (of: string, name: string): boolean => open !== null && open.of === of && open.name === name;
  const found = open === null ? undefined : open.of === "" ? library.find((one) => one.name === open.name) : callersOf(open.of).find((one) => one.name === open.name);
  const from = open === null ? undefined : open.of === "" ? source : open.of;
  const opened = found === undefined || from === undefined ? undefined : { persona: found, agent: from };
  const everyLibrary = agent === "" && opened !== undefined && isPinecalls(opened.persona);

  const own = slugs.flatMap((slug) => ownOf(callersOf(slug)).map((persona) => ({ persona, slug }))).sort((one, other) => one.persona.name.localeCompare(other.persona.name));
  const yours = own.filter((one) => matches(one.persona, search));
  const pinecalls = library.filter((one) => matches(one, search));
  const reading = !agentsRead || rosters.size < slugs.length;
  const refused = [...rosters.values()].flatMap((one) => (one.refused === null ? [] : [one.agent]));

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  const firstMine = yours[0];
  const firstTheirs = pinecalls[0];
  if (open === null && firstMine !== undefined) return <Navigate to={{ pathname: HOME, search: addressOf(firstMine.slug, firstMine.persona.name) }} replace />;
  if (open === null && firstTheirs !== undefined) return <Navigate to={{ pathname: HOME, search: addressOf(shelf, firstTheirs.name) }} replace />;

  const runsOf = (one: { persona: Persona; agent: string }): ReturnType<typeof callsOf> => (agent === "" && isPinecalls(one.persona) ? newestCallsOf(rosters.values(), one.persona.name) : callsOf(rosters.get(one.agent)?.runs ?? [], one.persona.name));

  return (
    <>
      <PageHead open={opened?.persona.name}>
        {opened !== undefined && (
          <PersonaActions
            key={`${opened.agent}/${opened.persona.name}`}
            persona={opened.persona}
            agent={opened.agent}
            agents={everyLibrary ? slugs : null}
            onEdit={() => setWriting({ kind: "form", agent: opened.agent, was: opened.persona })}
            onDropped={(callers) => {
              setCallers(opened.agent, callers);
              close();
            }}
          />
        )}
      </PageHead>
      <div className="app-layout ps-layout">
        <aside className="app-list" aria-label="Personas">
          <div className="app-list-head">
            <span className="app-list-title">Personas</span>
            <span className="dash-quiet">{reading ? "" : own.length + library.length}</span>
            {writable.length > 0 && (
              <span className="ps-list-moves">
                <button type="button" className="app-button ps-small" onClick={() => start("generate")}>
                  Generate
                </button>
                <button type="button" className="app-button ps-small" onClick={() => start("form")}>
                  New
                </button>
              </span>
            )}
          </div>
          <input className="app-input app-search" aria-label="Search personas" placeholder="Search personas" value={search} onChange={(event) => setSearch(event.target.value)} />
          <AgentPick agent={agent} onPick={(picked) => go({ [AGENT]: picked, [PERSONA]: "", [OF]: "" })} />
          <div className="app-rows">
            {yours.length > 0 && <span className="ps-shelf">Yours</span>}
            {yours.map(({ persona, slug }) => (
              <Row key={`${slug}/${persona.name}`} persona={persona} whose={agent === "" ? slug : undefined} last={callsOf(rosters.get(slug)?.runs ?? [], persona.name)[0]} open={isOpen(slug, persona.name)} to={{ pathname: HOME, search: addressOf(slug, persona.name) }} />
            ))}
            {pinecalls.length > 0 && <span className="ps-shelf">From Pinecall</span>}
            {pinecalls.map((persona) => (
              <Row key={persona.name} persona={persona} whose={undefined} last={(agent === "" ? newestCallsOf(rosters.values(), persona.name) : callsOf(rosters.get(agent)?.runs ?? [], persona.name))[0]} open={isOpen(shelf, persona.name)} to={{ pathname: HOME, search: addressOf(shelf, persona.name) }} />
            ))}
            {!reading && yours.length === 0 && pinecalls.length === 0 && <p className="dash-quiet app-none">Nothing by that name.</p>}
          </div>
        </aside>
        <div className="app-open">
          {refused.length > 0 && <p className="app-refused app-open-note">Could not read the personas of {refused.join(", ")}.</p>}
          {agentsRead && slugs.length === 0 ? (
            <div className="app-open-note">
              <div className="app-empty">
                <h2 className="app-name">No persona here yet</h2>
                <p className="dash-quiet">A persona is a caller a model plays against one of your agents. They show up here once you have an agent.</p>
              </div>
            </div>
          ) : opened !== undefined ? (
            <div className="app-main">
              <PersonaView persona={opened.persona} agent={opened.agent} showsAgents={agent === ""} on={agent !== "" && isPinecalls(opened.persona) && opened.persona.on} runs={runsOf(opened)} />
            </div>
          ) : (
            <p className="dash-quiet app-open-note">{reading ? "Reading…" : "Pick a persona to read it here."}</p>
          )}
        </div>
      </div>
      {writing?.kind === "form" && (
        <CallerFormPanel
          key={`${writing.agent}/${writing.was?.name ?? ""}`}
          agent={writing.agent}
          {...(writing.among === undefined ? {} : { among: writing.among })}
          was={writing.was}
          onSaved={(callers, name, whose) => {
            setCallers(whose, callers);
            setWriting(null);
            go({ [PERSONA]: name, [OF]: whose });
          }}
          onClose={shut}
        />
      )}
      {writing?.kind === "generate" && <ProposePanel key={writing.agent} agent={writing.agent} taken={new Set(callersOf(writing.agent).map((one) => one.name))} onKept={(callers) => setCallers(writing.agent, callers)} onClose={shut} />}
      {writing?.kind === "ask" && (
        <AskAgent
          title="Generate personas"
          about="A model writes personas from one agent's prompt, tools and knowledge. Pick which."
          agents={writable}
          onPick={(picked) => setWriting({ kind: "generate", agent: picked })}
          onClose={shut}
        />
      )}
    </>
  );
}

/** The address says whose personas (`?agent=`, none for every agent's) and which one is open (`?persona=`, read from `?of=`). */
export function PersonasPage(): ReactNode {
  const [params, setParams] = useSearchParams();
  const go = useCallback(
    (changes: Record<string, string>): void => {
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          for (const [name, value] of Object.entries(changes)) {
            if (value === "") next.delete(name);
            else next.set(name, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const agent = params.get(AGENT) ?? "";
  const name = params.get(PERSONA);
  // One page per agent in view: nothing read for one is ever drawn for another.
  return <Personas key={agent} agent={agent} open={name === null ? null : { name, of: params.get(OF) ?? "" }} go={go} />;
}
