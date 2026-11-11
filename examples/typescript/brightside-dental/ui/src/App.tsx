// Brightside's page: one call, drawn from the screen its agents put up. The page changes as the call does.

import { rowsOf, screenOf, type Screen as Drawn } from "@pinecall/room";
import { Screen, useKaraoke, useRoom } from "@pinecall/room/react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { PageContext, type Page } from "./page.js";
import { PARTS } from "./parts.js";

type Caller = "ana" | "new";

const DESKS: Record<string, string> = { front: "Front desk", billing: "Billing" };

/** The desk the screen's stage names; the front desk before any screen. */
function deskOf(screen: Drawn): string {
  const stage = screen.find((one) => typeof one !== "string" && one.part === "stage");
  const desk = typeof stage === "object" ? stage.props["desk"] : undefined;
  return typeof desk === "string" && desk in DESKS ? desk : "front";
}

export function App(): ReactNode {
  const [caller, setCaller] = useState<Caller>("new");
  const call = useRoom({
    tokens: async (scope, resume) => {
      const answer = await fetch("/api/token", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ scope, as: caller, resume }) });
      const body = await answer.json();
      if (!answer.ok) throw new Error(body.detail ?? `the server answered ${answer.status}`);
      return body;
    },
  });
  const screen = screenOf(call.log);
  const desk = deskOf(screen);
  const live = call.phase === "live";
  const page = useMemo<Page>(() => ({ live, tell: (name, data) => void call.event(name, data).catch(() => {}) }), [live, call.event]);
  const open = call.phase === "idle" || call.phase === "failed";

  return (
    <main data-desk={desk} data-phase={call.phase}>
      <header>
        <span className="brand">Brightside <em>Dental</em></span>
        {!open && <span className="desk" key={desk}>{DESKS[desk]}</span>}
        {(live || call.phase === "opening") && <button className="quiet" onClick={() => void call.leave()}>Hang up</button>}
      </header>

      {open ? (
        <Door caller={caller} pick={setCaller} error={call.phase === "failed" ? call.error : ""} start={(mode) => void call.start(mode)} />
      ) : (
        <>
          <section className="scene" key={sceneOf(screen)}>
            <PageContext.Provider value={page}>
              {call.phase === "opening" ? <p className="waiting">Connecting you to the front desk…</p> : <Screen screen={screen} parts={PARTS} />}
            </PageContext.Provider>
          </section>
          {call.phase === "ended" ? <Ended again={() => void call.start(call.mode === "talk" ? "talk" : "chat")} turns={rowsOf(call.log).flatMap((row) => (row.kind === "turn" ? [row] : []))} /> : <Voice call={call} />}
        </>
      )}
    </main>
  );
}

// The scene is keyed by its parts' names: a new part animates in, a prop that moved does not.
function sceneOf(screen: Drawn): string {
  const names = (drawn: Drawn): string => drawn.map((one) => (typeof one === "string" ? "" : `${one.part}(${names(one.children)})`)).join(",");
  return names(screen);
}

function Door({ caller, pick, error, start }: { caller: Caller; pick: (caller: Caller) => void; error: string; start: (mode: "talk" | "chat") => void }): ReactNode {
  return (
    <section className="door">
      <h1>
        The clinic's line,
        <br />
        on a page that <em>listens</em>.
      </h1>
      <p className="lede">Ask for a visit, or about a charge. The page follows the call: the agenda, a form, your ticket, your invoices.</p>
      <div className="who" role="radiogroup" aria-label="Who is calling">
        <button role="radio" aria-checked={caller === "new"} onClick={() => pick("new")}>
          <b>A new patient</b>
          <small>the clinic does not know you</small>
        </button>
        <button role="radio" aria-checked={caller === "ana"} onClick={() => pick("ana")}>
          <b>Ana Lopez</b>
          <small>known by her number, with invoices</small>
        </button>
      </div>
      <div className="start">
        <button className="primary" onClick={() => start("talk")}>Talk to the front desk</button>
        <button className="quiet" onClick={() => start("chat")}>or write instead</button>
      </div>
      {error !== "" && <p className="error">{error}</p>}
    </section>
  );
}

function Voice({ call }: { call: ReturnType<typeof useRoom> }): ReactNode {
  const said = useKaraoke(call.entries);
  const [line, setLine] = useState("");
  const turns = rowsOf(call.log).flatMap((row) => (row.kind === "turn" ? [row] : []));
  const last = turns.at(-1);
  const send = (event: FormEvent): void => {
    event.preventDefault();
    if (call.phase !== "live" || line.trim() === "") return;
    void call.send(line).catch(() => {});
    setLine("");
  };
  const speaking = call.speaking.agent ? "agent" : call.speaking.user ? "user" : "nobody";

  return (
    <footer>
      <div className="orb" data-speaking={speaking} style={{ ["--level" as string]: call.speaking.level.toFixed(2) }} aria-hidden />
      <p className="caption" aria-live="polite">
        {said !== null ? (
          <>
            <span>{said.lit}</span>
            <span className="coming">{said.coming}</span>
          </>
        ) : last !== undefined ? (
          <span className={last.role === "user" ? "yours" : ""}>{last.text}</span>
        ) : (
          <span className="coming">…</span>
        )}
      </p>
      {call.wantsSound && <button className="primary" onClick={call.playSound}>Tap to hear the call</button>}
      <form onSubmit={send}>
        <input value={line} onChange={(event) => setLine(event.target.value)} placeholder={call.mode === "talk" ? "Speak, or write here" : "Write to the front desk"} aria-label="Write to the agent" />
      </form>
    </footer>
  );
}

function Ended({ again, turns }: { again: () => void; turns: { key: string; role: "user" | "agent"; text: string }[] }): ReactNode {
  return (
    <footer className="ended">
      <p className="over">The call is over. This is what was said.</p>
      <ol className="said">
        {turns.map((turn) => (
          <li key={turn.key} data-role={turn.role}>{turn.text}</li>
        ))}
      </ol>
      <button className="primary" onClick={again}>Call again</button>
    </footer>
  );
}
