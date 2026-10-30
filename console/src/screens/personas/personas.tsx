/** Personas: the callers as a grid of faces — the agent in view's, or every agent's — and the one chosen read, or written, with its runs beside it. */

import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { ownedAt, rowAt, useHarnessAgents } from "../../lib/harness";
import { usePane } from "../../ui";
import { isPinecalls, ownedByTheClass, readPersonas, switchPersona, type Persona } from "./door";
import { Generate } from "./generate";
import { PersonaEditor } from "./persona-editor";
import { PersonaView } from "./persona-view";
import { Overview } from "./overview";
import { RunsSide } from "./runs-side";
import { usePersonas } from "./use-personas";
import { useRunStandings } from "./use-run-standings";
import "./personas.css";

/**
 * One screen whoever is in view. A caller is written to test ONE agent — the patient who cancels is
 * the clinic's — and the gateway keeps them so (`/v1/agents/<agent>/personas`); with every agent in
 * view the roster is every agent's (`/v1/personas`), each under its agent's name. The URL says which
 * one is open: `/a/<agent>/personas/<name>`, or `/personas/<agent>/<name>` with every agent in view;
 * `?edit=1` that one being written, `?new=1` a new one. What this page writes is what `pinecall
 * simulate --persona` finds, in every console, with no deploy between.
 */
export function Personas(): ReactNode {
  const params = useParams();
  const agent = params["agent"] ?? "";
  const owner = params["owner"] ?? agent;
  const named = params["call"];
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const credentials = useCredentials();
  // The runs pane stands beside a caller being read, as the floor's does beside the call it watches.
  const runs = usePane({ name: "personas.runs", initial: 340, min: 280, max: 560, side: "right" });
  const { personas: kept, asking, setPersonas, reread } = usePersonas(agent);
  // The class owns the roster: its files and its switches, read when it registers; nothing is written here.
  const fixed = agent !== "" && ownedByTheClass(kept ?? []);
  // With every agent in view, the org's agents' callers: the ones Viewing offers, and no other slug.
  const theOrgs = useHarnessAgents(agent);
  // Pinecall's library is switched per agent, so the org's list carries none: with every agent in
  // view it is shown as the first agent reads it, its switches left to an agent in view.
  const library = useLibrary(agent === "" ? (theOrgs?.[0] ?? null) : null);
  const personas = kept === null || theOrgs === null ? null : [...kept.filter((one) => theOrgs.includes(one.agent)), ...library];
  // What every caller has done, read once here for the overview's standing.
  const standings = useRunStandings(personas);
  const adding = search.get("new") === "1";
  const generating = search.get("generate") === "1";
  const editing = search.get("edit") === "1";
  const chosen = named === undefined ? undefined : personas?.find((one) => one.agent === owner && one.name === named);
  // The caller being READ, which is the only state the runs pane stands beside.
  const reading = chosen !== undefined && !adding && !editing && !generating ? chosen : null;
  // Whom a new caller may be written for: the agent in view, or any agent of the org.
  const owners = [...(theOrgs ?? [])].sort();

  const go = (persona: Pick<Persona, "agent" | "name"> | null, how: "" | "edit" | "new" | "generate" = ""): void => {
    const asked = how === "" ? "" : `?${how}=1`;
    void navigate(`${persona === null ? rowAt(agent, "personas") : ownedAt(agent, "personas", persona.agent, persona.name)}${asked}`);
  };
  // A write answers with its agent's list: one agent in view takes it whole, every agent reads all again.
  const saved = (read: Persona[], written: Pick<Persona, "agent" | "name">): void => {
    if (agent === "") reread();
    else setPersonas(read);
    go(written);
  };

  // One of Pinecall's switched from its card: the agent's list after it, nothing opened.
  const switched = (one: Persona, on: boolean): void => {
    void switchPersona(credentials, one.agent, one.name, on).then((read) => {
      if (agent === "") reread();
      else setPersonas(read);
    });
  };

  return (
    <div className="psn">
      {/* The runs stand beside a caller being READ: while the form is open the screen is about
          writing one, and the pane would only squeeze the fields. */}
      <div className={reading === null ? "psn-right" : "psn-right psn-right-runs"} style={runs.style}>
        {reading !== null && runs.handle}
        <main className="psn-main">
          {generating && agent !== "" ? (
            <Generate agent={agent} personas={personas ?? []} keptAs={fixed ? "files" : "rows"} onKept={(read) => setPersonas(read)} onCancel={() => go(null)} />
          ) : adding ? (
            <PersonaEditor key="new" owners={owners} was={undefined} onSaved={saved} onCancel={() => go(chosen ?? null)} />
          ) : personas === null ? (
            <p className="psn-empty">{asking ?? "Asking the gateway…"}</p>
          ) : chosen === undefined ? (
            <Overview agent={agent} personas={personas ?? []} standings={standings} fixed={fixed} onNew={() => go(null, "new")} onGenerate={() => go(null, "generate")} onSwitch={switched} />
          ) : editing ? (
            <PersonaEditor key={`${chosen.agent}/${chosen.name}`} owners={[chosen.agent]} was={chosen} onSaved={saved} onCancel={() => go(chosen)} />
          ) : (
            <PersonaView
              key={`${chosen.agent}/${chosen.name}`}
              inView={agent}
              persona={chosen}
              fixed={fixed}
              onEdit={() => go(chosen, "edit")}
              onDropped={(read) => {
                if (agent === "") reread();
                else setPersonas(read);
                go(null);
              }}
              onSwitched={(read) => {
                if (agent === "") reread();
                else setPersonas(read);
              }}
            />
          )}
        </main>
        {reading !== null && <RunsSide key={`${reading.agent}/${reading.name}`} inView={agent} persona={reading} />}
      </div>
    </div>
  );
}

/** Pinecall's personas as one agent reads them, for the every-agent view; none when no agent is named. */
function useLibrary(agent: string | null): Persona[] {
  const credentials = useCredentials();
  const [library, setLibrary] = useState<Persona[]>([]);
  useEffect(() => {
    if (agent === null) {
      setLibrary([]);
      return;
    }
    let gone = false;
    readPersonas(credentials, agent).then(
      (read) => {
        if (!gone) setLibrary(read.filter(isPinecalls));
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);
  return library;
}
