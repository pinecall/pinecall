/** Simulations: the callers to choose from, and in a tab of their own the simulations already run; one open is the whole screen — heard live, both sides, and read as it happens. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { useListen } from "@pinecall/core/use-listen";
import { useRoomOpen } from "@pinecall/core/use-room-open";
import { useSupervise } from "@pinecall/core/use-supervise";
import { rowAt } from "../../lib/harness";
import { useOrg } from "../../lib/org";
import { useScopes } from "../../lib/whoami";
import { percent, usd } from "../../lib/format";
import { Button, Page, PageHead, Stat, Stats, Tabs } from "../../ui";
import { RunsTable } from "./runs";
import { Starter } from "./starter";
import { useRuns } from "./use-runs";
import { isPinecalls } from "../personas/door";
import { usePersonas } from "../personas/use-personas";
import { Call } from "../call";
import "./simulations.css";

/**
 * One screen whoever is in view: a simulation is started by choosing a caller and watched right
 * here, and every one already run is listed in Past runs (`?tab=runs`) — the agent in view's, or
 * every agent's — and opens in the same place. The URL names the call (`/a/<agent>/simulations/<call>?spoken=1`, or
 * `/simulations/<call>` with every agent in view), so a reload lands on the same call. A spoken one
 * is heard the moment its room opens — the caller the model plays and the agent, one ear on both.
 */
export function Simulations(): ReactNode {
  const inView = useParams()["agent"] ?? "";
  const call = useParams()["call"];
  const [search, setSearch] = useSearchParams();
  const tab: Tab = search.get("tab") === "runs" ? "runs" : "call";
  const navigate = useNavigate();
  const { agents } = useOrg();
  const spoken = search.get("spoken") === "1";
  const preferred = search.get("persona") ?? undefined;
  // Who is in view is the sidebar's to say, and nothing here narrows it further: with one agent in
  // view, its callers; with every agent, every agent's own callers, each ringing the agent it was
  // written for. Pinecall's library is one list for every agent, so with every agent in view it
  // rings the agent picked beside it — the one the link named, else the org's first running agent.
  const [picked, setPicked] = useState(search.get("agent") ?? "");
  const agent = inView !== "" ? inView : picked !== "" ? picked : (agents[0]?.slug ?? "");
  const everyones = usePersonas(inView === "" ? "" : inView);
  const ringers = usePersonas(inView === "" && agent !== "" ? agent : null);
  const personas =
    inView !== "" ? everyones.personas : everyones.personas === null ? null : [...everyones.personas.filter((one) => !isPinecalls(one)), ...(ringers.personas ?? []).filter(isPinecalls)];
  const asking = everyones.asking ?? ringers.asking;
  // Every start reads the list again, so the new one is at its top.
  const [round, setRound] = useState(0);

  const read = useRuns(inView, round);
  const [opening, setOpening] = useState(false);

  const started = (next: string, voice: boolean): void => {
    setRound((one) => one + 1);
    void navigate(`${rowAt(inView, "simulations")}/${next}${voice ? "?spoken=1" : ""}`);
  };

  // A call open is the whole screen: its transcript, its ear, and the one move it has. Nothing open
  // is the page to start one from, and the simulations already run below it.
  if (call !== undefined) {
    return (
      <div className="sims-watch" key={call}>
        <Link className="sims-back" to={rowAt(inView, "simulations")}>
          ← Simulations
        </Link>
        {spoken && <Ear call={call} />}
        {/* The desk belongs to a supervisor on somebody's real call: whisper, say, take the
            line, transfer. Nobody is on this one — a model is playing both ends — so the screen
            is the transcript and the one move it has, which is to stop the thing. */}
        <Call call={call} supervised={false} beside={(over) => <Stop call={call} spoken={spoken} over={over} />} />
      </div>
    );
  }
  const runs = read.runs ?? [];
  const judged = runs.filter((run) => run.score !== null);
  const held = judged.filter((run) => run.score?.passed === true).length;
  const cost = runs.reduce((sum, run) => sum + (run.cost_usd ?? 0), 0);
  // Every caller is offered when asked for, or when a link named one.
  const choosing = opening || preferred !== undefined;
  const pick = (next: Tab): void => {
    const kept = new URLSearchParams(search);
    if (next === "runs") kept.set("tab", "runs");
    else kept.delete("tab");
    setSearch(kept, { replace: true });
  };
  return (
    <Page>
      <PageHead
        title="Simulations"
        lede="A model plays a persona against the agent, improvising every line from its goal, its manner and its own facts — written, or on a real line you can hear. Choose who calls and it starts."
        ledeWidth={600}
        actions={
          tab === "call" && (
            <Button size="base" onClick={() => setOpening(!choosing)}>
              {choosing ? "Only the ones switched on" : "All callers"}
            </Button>
          )
        }
      />
      <Tabs label="Simulations" tabs={[{ tab: "call", name: "New simulation" }, { tab: "runs", name: "Past runs", mark: read.runs === null ? undefined : <span className="sims-count">{read.total}</span> }]} on={tab} onPick={pick} />
      {tab === "call" && (
        <Starter
          inView={inView}
          agents={agents.map((one) => one.slug)}
          agent={agent}
          onAgent={setPicked}
          personas={personas}
          asking={asking}
          asked={preferred}
          all={choosing}
          onStarted={started}
        />
      )}
      {tab === "runs" && (
        <>
          <Stats min={170}>
            <Stat label="Simulations" value={read.runs === null ? "—" : read.total} of={read.runs === null ? undefined : "in all"} />
            <Stat label="Held" value={judged.length === 0 ? "—" : percent(held / judged.length)} of={judged.length === 0 ? undefined : `${String(held)} of ${String(judged.length)} judged`} />
            <Stat label="Cost of these" value={read.runs === null ? "—" : usd(cost)} of={read.runs === null ? undefined : `${String(runs.length)} read`} />
            <Stat label="On a call" value={runs.filter((run) => run.ended_at === null).length} />
          </Stats>
          <RunsTable inView={inView} read={read} />
        </>
      )}
    </Page>
  );
}

type Tab = "call" | "runs";

// Stopping a simulation is hanging its call up, and there is no second door for it: the persona
// is played in the gateway off this call's own log, and `call.ended` is where it learns to stop
// talking (runtime api/evals/voice.py). So the agent, the app and this button all stop it alike.
/** The one move this screen has on a running simulation: end the call, and the caller with it. */
function Stop({ call, spoken, over }: { call: string; spoken: boolean; over: boolean }): ReactNode {
  const scopes = useScopes();
  const desk = useSupervise(call, spoken);
  const [stopping, setStopping] = useState(false);

  if (over) return <span className="sims-stopped">the simulation is over</span>;
  // Hanging a call up is a supervisor's verb wherever it is pressed, and `qa` is the one role that
  // runs simulations without that scope: it is told so, rather than handed a button the gateway
  // answers 403 to.
  if (scopes !== null && !scopes.includes("supervise")) {
    return <span className="sims-stopped">a key that supervises stops a simulation</span>;
  }
  // A refusal puts the button back: the call is still running and the person may try again.
  const sent = stopping && desk.error === null;
  return (
    <>
      <Button
        size="sm"
        kind="danger"
        disabled={sent}
        onClick={() => {
          setStopping(true);
          void desk.end();
        }}
      >
        {sent ? "Stopping…" : "Stop"}
      </Button>
      {desk.error !== null && <span className="sims-refused">{desk.error}</span>}
    </>
  );
}

// A spoken simulation's room opens a moment after the call has its id; the call's own log says
// when (`room.opened`), and the ear joins once then. A join the door refuses is shown, never retried.
/** One ear on the whole room, the caller's track and the agent's, joined and unmuted on its own. */
function Ear({ call }: { call: string }): ReactNode {
  const ear = useListen(call);
  const room = useRoomOpen(call);
  const inside = useRef(false);
  const knocked = useRef(false);

  useEffect(() => {
    if (room === "open" && ear.listening === "off" && !knocked.current) {
      knocked.current = true;
      void ear.join();
    }
    // In the room: heard at once — this screen is for listening, not for reading first.
    if (ear.listening === "muted" && !inside.current) {
      inside.current = true;
      ear.hear(true);
    }
  }, [ear, room]);

  const said = ((): string => {
    switch (ear.listening) {
      case "on":
        return "Listening live · the caller and the agent";
      case "muted":
        return "Muted";
      case "joining":
        return "Joining the call…";
      case "failed":
        return `Could not join the call: ${ear.error ?? "no room"}`;
      case "off":
        if (inside.current || room === "over") return "The call is over";
        return room === "open" ? "Joining the call…" : "Waiting for the call's room to open…";
      case "over":
        return "The call is over";
    }
  })();

  return (
    <div className="sims-ear" role="status">
      <span className={ear.listening === "on" ? "sims-ear-dot sims-ear-dot-on" : "sims-ear-dot"} />
      <span className="sims-ear-said">{said}</span>
      {ear.listening === "on" && (
        <Button size="sm" pill onClick={() => ear.hear(false)}>
          Mute
        </Button>
      )}
      {ear.listening === "muted" && (
        <Button size="sm" pill onClick={() => ear.hear(true)}>
          Unmute
        </Button>
      )}
    </div>
  );
}
