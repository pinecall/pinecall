/** Starting simulations: tick who calls, say how many calls each and how the line is (written, quiet or noisy), and run them — each one put on the agent and judged when it ends. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { usd } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { Chips, Icon, Input, Segmented, Select, SelectItem } from "../../ui";
import { isPinecalls, type Persona } from "../personas/door";
import { PlayedBy, type Played } from "../personas/played-by";
import { Callers, keyOf } from "./callers";
import { playedBy, startSimulation } from "./simulating";
import "./starter.css";

// How many turns a caller improvises when nobody said: the same fifteen `pinecall simulate` uses.
// Six was the length of a walkthrough and not of a call: every simulation tested the opening of an
// agent and the end of none.
const TURNS = 15;

// The television behind the caller at the level the hearing calls measured, and no packets lost:
// the same defaults the terminal verb has, so the two doors spoil a line the same way.
const NOISE_DB = 15;
const LOSS_PERCENT = 0;

// What plays behind the caller on a noisy line; "" is the persona's own ambience, a television for one that names none.
const BACKGROUNDS = [
  { value: "", label: "The caller's own background" },
  { value: "television", label: "A television" },
  { value: "cafe", label: "A café" },
  { value: "office", label: "An office" },
  { value: "street", label: "A street" },
] as const;

type Background = (typeof BACKGROUNDS)[number]["value"];

// Nobody chosen: each caller is played as its persona says.
const THE_PERSONAS: Played = { llm: "", tts: "", voice: "" };
const UNSAID = { llm: "Each persona's own model", tts: "Each persona's own voice" };

// The line is written, or spoken — quiet, or with a voice and the street behind it.
type Line = "written" | "quiet" | "noisy";

const LINES: readonly { value: Line; label: string }[] = [
  { value: "written", label: "Written" },
  { value: "quiet", label: "Quiet" },
  { value: "noisy", label: "Noisy" },
];

const EACH: readonly { value: "1" | "3" | "5"; label: string }[] = [
  { value: "1", label: "1" },
  { value: "3", label: "3" },
  { value: "5", label: "5" },
];

/** What a call of these has cost and taken so far: the estimate under the button, read off the runs already made. */
export interface Typical {
  seconds: number | null;
  usd: number | null;
}

/**
 * The gateway plays each caller and calls the agent as anybody calls it, so whatever holds the
 * agent answers — the one deployed, or a `pinecall start` in its directory — and every call is
 * judged at hang-up like any other. One call started opens at once; several stay here, in Runs.
 */
export function Starter({
  inView,
  agents,
  agent,
  onAgent,
  personas,
  asking,
  asked,
  typical,
  onStarted,
}: {
  /** The agent in view, or "" for every agent: with one in view, the agent is it. */
  inView: string;
  /** The agents a caller may be put on: the ones a process holds right now. */
  agents: readonly string[];
  /** The agent Pinecall's callers ring: the one in view, else the one picked beside the library. */
  agent: string;
  onAgent: (agent: string) => void;
  /** The callers, as the screen read them — every agent's own with every agent in view; null while asked or refused. */
  personas: Persona[] | null;
  /** Why there are none yet: still asking, or the refusal in the gateway's words. */
  asking: string | null;
  /** The caller the page was opened for (Personas' "Use in a simulation"), ticked from the start. */
  asked?: string | undefined;
  typical: Typical;
  /** Told the calls' ids the moment there are some, and whether they are on a spoken line. */
  onStarted: (calls: string[], spoken: boolean) => void;
}): ReactNode {
  const credentials = useCredentials();
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const [each, setEach] = useState<"1" | "3" | "5">("1");
  // The screen is for listening: a spoken line unless somebody wants a written one.
  const [line, setLine] = useState<Line>("quiet");
  const [turns, setTurns] = useState(TURNS);
  const [noise, setNoise] = useState(NOISE_DB);
  const [loss, setLoss] = useState(LOSS_PERCENT);
  const [background, setBackground] = useState<Background>("");
  const [played, setPlayed] = useState<Played>(THE_PERSONAS);
  const [choosing, setChoosing] = useState(false);
  const [all, setAll] = useState(asked !== undefined);
  const [calling, setCalling] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const spoken = line !== "written";

  // A caller the page was opened for starts ticked, once the callers are read.
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || asked === undefined || personas === null) return;
    seeded.current = true;
    setPicked(new Set(personas.filter((one) => one.name === asked).map(keyOf)));
  }, [asked, personas]);

  const chosen = (personas ?? []).filter((persona) => picked.has(keyOf(persona)));
  const total = chosen.length * Number(each);
  const hasOff = (personas ?? []).some((persona) => isPinecalls(persona) && !persona.on);

  const toggle = (persona: Persona): void => {
    const next = new Set(picked);
    if (next.has(keyOf(persona))) next.delete(keyOf(persona));
    else next.add(keyOf(persona));
    setPicked(next);
  };

  const run = async (): Promise<void> => {
    if (calling || total === 0) return;
    setCalling(true);
    setRefused(null);
    const calls: string[] = [];
    try {
      for (const persona of chosen) {
        for (let at = 0; at < Number(each); at += 1) {
          // An agent's own caller rings the agent it was written for; Pinecall's ring the one picked.
          calls.push(
            await startSimulation(credentials, {
              agent: isPinecalls(persona) || inView !== "" ? agent : persona.agent,
              persona: persona.name,
              voice: spoken,
              turns,
              ...playedBy(played),
              ...(line === "noisy" ? { interferer_db: noise, packet_loss: loss / 100, ...(background === "" ? {} : { ambience: background }) } : {}),
            }),
          );
        }
      }
    } catch (failed) {
      // What was refused is said, and what had started stays started: the screen carries on with those.
      const said = failed instanceof GatewayError ? failed.message : String(failed);
      setRefused(calls.length === 0 ? said : `${said} — ${String(calls.length)} of ${String(total)} started.`);
    } finally {
      setCalling(false);
    }
    if (calls.length > 0) onStarted(calls, spoken);
  };

  const minutes = typical.seconds === null ? null : Math.max(1, Math.round(typical.seconds / 60));
  const cost = typical.usd === null ? null : typical.usd * total;

  return (
    <section className="sim-card" aria-label="new simulation">
      <div className="sim-card-title">New simulation</div>
      <div className="sim-who">
        <div className="sim-who-head">
          <span className="sim-label">Who calls</span>
          <span className="sim-who-links">
            {hasOff && (
              <button type="button" className="sim-link" onClick={() => setAll(!all)}>
                {all ? "Only the ones switched on" : "Show the ones switched off"}
              </button>
            )}
            <Link to={rowAt(inView, "personas")}>Edit personas</Link>
          </span>
        </div>
        {agents.length === 0 && <p className="sim-note">No agent is running in this world: deploy one, or run pinecall start in its directory.</p>}
        {personas === null && asking !== null && <p className="sim-note">{asking}</p>}
        {personas !== null && personas.length === 0 && <p className="sim-note">No personas yet: write the first caller in Personas.</p>}
        {personas !== null && personas.length > 0 && <Callers inView={inView} agents={agents} agent={agent} onAgent={onAgent} personas={personas} picked={picked} onPick={toggle} all={all} />}
      </div>

      <div className="sim-options">
        <div className="sim-option">
          <span className="sim-label">Calls per persona</span>
          <Chips options={EACH} value={each} onChange={setEach} />
        </div>
        <div className="sim-option">
          <span className="sim-label">The line</span>
          <Segmented options={LINES} value={line} onChange={setLine} />
        </div>
        <div className="sim-option">
          <span className="sim-label">Turns each</span>
          <Input size="sm" type="number" aria-label="Turns the caller says" min={1} max={30} value={turns} onChange={(event) => setTurns(Number(event.target.value))} />
        </div>
      </div>
      {line === "noisy" && (
        <div className="sim-noise">
          <Select size="sm" value={background} onValueChange={(value) => setBackground(value as Background)} aria-label="What plays behind the caller">
            {BACKGROUNDS.map((one) => (
              <SelectItem key={one.value} value={one.value}>
                {one.label}
              </SelectItem>
            ))}
          </Select>
          <label className="sim-turns">
            <Input size="sm" type="number" aria-label="Noise, dB under" min={0} max={60} value={noise} onChange={(event) => setNoise(Number(event.target.value))} />
            <span>dB under</span>
          </label>
          <label className="sim-turns">
            <Input size="sm" type="number" aria-label="Packets lost, %" min={0} max={100} value={loss} onChange={(event) => setLoss(Number(event.target.value))} />
            <span>% lost</span>
          </label>
        </div>
      )}

      <div className="sim-played">
        <button
          type="button"
          className="sim-link"
          onClick={() => {
            // Closed is the personas' own again, never a choice left behind out of sight.
            if (choosing) setPlayed(THE_PERSONAS);
            setChoosing(!choosing);
          }}
        >
          {choosing ? "Play each caller as its persona says" : "Played by: each persona's own model and voice · change for this run"}
        </button>
        {choosing && (
          <>
            <PlayedBy played={played} onChange={setPlayed} unsaid={UNSAID} />
            <p className="sim-note">For these calls alone; the personas keep their own. The callers run on the runtime's keys unless you brought that vendor's, and each call counts as one simulation.</p>
          </>
        )}
      </div>

      {refused !== null && <p className="sim-refused">{refused}</p>}
      <div className="sim-foot">
        <span className="sim-foot-said">
          {total === 0
            ? "Tick who calls to run."
            : [`${String(total)} ${total === 1 ? "call" : "calls"}`, minutes === null ? null : `about ${String(minutes)} min each`, cost === null ? null : `around ${usd(cost)}`, "judged when each one ends"].filter((part) => part !== null).join(" · ")}
        </span>
        <button type="button" className="sim-run" disabled={calling || total === 0} onClick={() => void run()}>
          <Icon name="play" size={14} />
          {calling ? "Starting…" : total === 0 ? "Run" : `Run ${String(total)} ${total === 1 ? "call" : "calls"}`}
        </button>
      </div>
    </section>
  );
}
