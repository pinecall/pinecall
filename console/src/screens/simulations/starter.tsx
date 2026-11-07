/** Starting simulations: tick who calls and say how the line is (written, quiet or noisy), and run them — each one put on the agent and judged when it ends. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { usd } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { WORLD } from "../../lib/mode";
import { Icon, Input, Segmented, Select, SelectItem, type IconName } from "../../ui";
import { isPinecalls, type Persona } from "../personas/door";
import { PlayedBy, type Played } from "../personas/played-by";
import { Callers, keyOf } from "./callers";
import { AgainstRows, twoRows } from "./against";
import { COMPARED_AT_MOST, startComparison, trimmed, type AgentValues } from "./comparing";
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

const LINES: readonly { value: Line; icon: IconName; title: string; sub: string }[] = [
  { value: "written", icon: "keyboard", title: "Chat", sub: "Typed, the fastest. Uses no call minutes." },
  { value: "quiet", icon: "phone", title: "Phone call", sub: "Spoken out loud, on a clear line." },
  { value: "noisy", icon: "speaker", title: "Noisy phone call", sub: "Spoken, with a TV or a street behind the caller." },
];

// How long the caller talks: the turns it improvises before it hangs up, at most thirty.
const LENGTHS: readonly { value: string; label: string }[] = [
  { value: "6", label: "Short" },
  { value: String(TURNS), label: "Normal" },
  { value: "30", label: "Long" },
];

// The gateway holds an org to this many simulated calls on the line at once in a world: a run of
// more starts these and says so, and the rest are started once one ends.
const AT_ONCE = 10;

// What the form does: several callers, each its own call; or each caller ticked against the agent
// under several configurations, one call per pair, read as one table. Production has neither: one caller, one call, a check
// of the agent as it is deployed.
type Doing = "run" | "compare";

const DOINGS: readonly { value: Doing; icon: IconName; title: string; sub: string }[] = [
  { value: "run", icon: "headphones", title: "Run callers", sub: "Pretend callers ring your agent, each call judged when it ends." },
  { value: "compare", icon: "scale", title: "Compare models", sub: "The same callers against two or more setups, side by side." },
];

const CHECKING = WORLD === "production";

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
  /** Told the calls' ids the moment there are some, whether they are on a spoken line, and the comparison they are, when they are one. */
  onStarted: (calls: string[], spoken: boolean, comparison?: string) => void;
}): ReactNode {
  const credentials = useCredentials();
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  // The screen is for listening: a spoken line unless somebody wants a written one.
  const [line, setLine] = useState<Line>("quiet");
  const [turns, setTurns] = useState(TURNS);
  const [noise, setNoise] = useState(NOISE_DB);
  const [loss, setLoss] = useState(LOSS_PERCENT);
  const [background, setBackground] = useState<Background>("");
  const [played, setPlayed] = useState<Played>(THE_PERSONAS);
  const [choosing, setChoosing] = useState(false);
  // A comparison: each caller ticked, the agent under each of these, placed together.
  const [comparing, setComparing] = useState(false);
  const [against, setAgainst] = useState<AgentValues[]>(twoRows);
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

  // A caller written for an agent no process holds cannot ring it: it is not offered.
  const held = (personas ?? []).filter((persona) => isPinecalls(persona) || agents.includes(persona.agent));
  const unheld = (personas ?? []).length - held.length;
  const chosen = held.filter((persona) => picked.has(keyOf(persona)));
  const total = chosen.length;
  const hasOff = held.some((persona) => isPinecalls(persona) && !persona.on);

  // An agent's own caller rings the agent it was written for; Pinecall's ring the one picked.
  const ringing = (persona: Persona): string => (isPinecalls(persona) || inView !== "" ? agent : persona.agent);

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
    if (comparing) {
      await compare();
      return;
    }
    const calls: string[] = [];
    try {
      for (const persona of chosen) {
        calls.push(
          await startSimulation(credentials, {
            agent: ringing(persona),
            persona: persona.name,
            voice: spoken,
            turns,
            ...playedBy(played),
            ...(line === "noisy" ? { interferer_db: noise, packet_loss: loss / 100, ...(background === "" ? {} : { ambience: background }) } : {}),
          }),
        );
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

  // Each caller ticked, the agent under each configuration: the gateway places one call per pair at
  // once and says which were refused; the ones that started are the comparison.
  const compare = async (): Promise<void> => {
    const [persona, ...more] = chosen;
    const rung = new Set(chosen.map(ringing));
    if (persona === undefined || rung.size !== 1) {
      setRefused(persona === undefined ? "Tick a caller to compare." : "A comparison rings one agent: tick callers of the same agent.");
      setCalling(false);
      return;
    }
    try {
      const started = await startComparison(credentials, {
        agent: ringing(persona),
        persona: persona.name,
        ...(more.length === 0 ? {} : { more_personas: more.map((one) => one.name) }),
        voice: spoken,
        turns,
        ...playedBy(played),
        ...(line === "noisy" ? { interferer_db: noise, packet_loss: loss / 100, ...(background === "" ? {} : { ambience: background }) } : {}),
        against: against.map(trimmed),
      });
      if (started.refused.length > 0) setRefused(started.refused.map((one) => one.why).join(" · "));
      if (started.calls.length > 0) onStarted(started.calls.map((one) => one.call), spoken, started.comparison);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setCalling(false);
    }
  };

  const minutes = typical.seconds === null ? null : Math.max(1, Math.round(typical.seconds / 60));
  const placed = comparing ? total * against.length : total;
  const cost = typical.usd === null ? null : typical.usd * placed;
  // A check is one call: more than one caller ticked runs nothing. A comparison is a call per caller and configuration, ten at most.
  const oneOnly = CHECKING;
  const tooMany = comparing && placed > COMPARED_AT_MOST;

  return (
    <section className="sim-card" aria-label={CHECKING ? "check call" : "new simulation"}>
      <div className="sim-card-title">{CHECKING ? "Check call" : "New simulation"}</div>
      {CHECKING ? (
        <p className="sim-note">One caller, one call against the agent as it is deployed, on production&apos;s keys and knowledge, judged at hang-up. To compare models or play several callers, use the sandbox.</p>
      ) : (
        <div className="sim-doings" role="radiogroup" aria-label="What to run">
          {DOINGS.map((one) => (
            <button key={one.value} type="button" role="radio" aria-checked={(one.value === "compare") === comparing} className={(one.value === "compare") === comparing ? "sim-doing sim-doing-on" : "sim-doing"} onClick={() => setComparing(one.value === "compare")}>
              <span className="sim-doing-icon">
                <Icon name={one.icon} size={16} />
              </span>
              <span className="sim-doing-title">{one.title}</span>
              <span className="sim-doing-sub">{one.sub}</span>
            </button>
          ))}
        </div>
      )}

      <div className="sim-step">
        <div className="sim-step-head">
          <span className="sim-label">
            <Icon name="users" size={14} />
            {oneOnly ? "Who calls · pick one" : "Who calls"}
          </span>
          <span className="sim-who-links">
            {hasOff && (
              <button type="button" className="sim-link" onClick={() => setAll(!all)}>
                {all ? "Hide the ones switched off" : "Show the ones switched off"}
              </button>
            )}
            <Link to={rowAt(inView, "personas")}>Edit personas</Link>
          </span>
        </div>
        {agents.length === 0 && <p className="sim-note">No agent is running right now. Start or deploy one, and its callers show up here.</p>}
        {personas === null && asking !== null && <p className="sim-note">{asking}</p>}
        {personas !== null && personas.length === 0 && <p className="sim-note">No callers yet: write the first one in Personas.</p>}
        {personas !== null && held.length > 0 && <Callers inView={inView} agents={agents} agent={agent} onAgent={onAgent} personas={held} picked={picked} onPick={toggle} all={all} />}
        {unheld > 0 && (
          <p className="sim-note">
            {String(unheld)} more {unheld === 1 ? "caller belongs" : "callers belong"} to agents that are not running right now.
          </p>
        )}
      </div>

      {comparing && (
        <div className="sim-step">
          <div className="sim-step-head">
            <span className="sim-label">
              <Icon name="scale" size={14} />
              Setups to compare
            </span>
            <span className="sim-note">Same callers, a different agent in each. Results come back side by side, best first.</span>
          </div>
          <AgainstRows rows={against} onChange={setAgainst} />
        </div>
      )}

      <div className="sim-step">
        <span className="sim-label">
          <Icon name="phone" size={14} />
          How they call
        </span>
        <div className="sim-doings" role="radiogroup" aria-label="How they call">
          {LINES.map((one) => (
            <button key={one.value} type="button" role="radio" aria-checked={line === one.value} className={line === one.value ? "sim-doing sim-doing-on" : "sim-doing"} onClick={() => setLine(one.value)}>
              <span className="sim-doing-icon">
                <Icon name={one.icon} size={16} />
              </span>
              <span className="sim-doing-title">{one.title}</span>
              <span className="sim-doing-sub">{one.sub}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="sim-length">
        <span className="sim-label">
          <Icon name="wave" size={14} />
          How long
        </span>
        <Segmented options={LENGTHS} value={String(turns)} onChange={(picked) => setTurns(Number(picked))} />
        <span className="sim-note">The caller says up to {String(turns)} things, then hangs up.</span>
      </div>

      {(line === "noisy" || !CHECKING) && (
        <details className="sim-more" open={choosing || line === "noisy" ? true : undefined}>
          <summary>More options</summary>
          <div className="sim-more-body">
            {line === "noisy" && (
              <div className="sim-noise">
                <span className="sim-label">The noise</span>
                <Select size="sm" value={background} onValueChange={(value) => setBackground(value as Background)} aria-label="What plays behind the caller">
                  {BACKGROUNDS.map((one) => (
                    <SelectItem key={one.value} value={one.value}>
                      {one.label}
                    </SelectItem>
                  ))}
                </Select>
                <label className="sim-turns">
                  <Input size="sm" type="number" aria-label="Noise, dB under" min={0} max={60} value={noise} onChange={(event) => setNoise(Number(event.target.value))} />
                  <span>dB under the voice</span>
                </label>
                <label className="sim-turns">
                  <Input size="sm" type="number" aria-label="Packets lost, %" min={0} max={100} value={loss} onChange={(event) => setLoss(Number(event.target.value))} />
                  <span>% of the line lost</span>
                </label>
              </div>
            )}
            {!CHECKING && (
              <div className="sim-played">
                <label className="sim-check">
                  <input
                    type="checkbox"
                    checked={choosing}
                    onChange={() => {
                      // Unticked is the personas' own again, never a choice left behind out of sight.
                      if (choosing) setPlayed(THE_PERSONAS);
                      setChoosing(!choosing);
                    }}
                  />
                  Play the callers on another model or voice
                </label>
                {choosing && (
                  <>
                    <PlayedBy played={played} onChange={setPlayed} unsaid={UNSAID} />
                    <p className="sim-note">For these calls alone; the personas keep their own.</p>
                  </>
                )}
              </div>
            )}
          </div>
        </details>
      )}

      {refused !== null && <p className="sim-refused">{refused}</p>}
      <div className="sim-foot">
        <span className="sim-foot-said">
          {total === 0
            ? oneOnly
              ? "Tick one caller."
              : "Tick who calls to run."
            : [
                `${String(placed)} ${placed === 1 ? "call" : "calls"}`,
                tooMany ? `a comparison is ${String(COMPARED_AT_MOST)} calls at most: fewer callers or configurations` : null,
                !comparing && placed > AT_ONCE ? `${String(AT_ONCE)} at once at most` : null,
                minutes === null ? null : `about ${String(minutes)} min each`,
                cost === null ? null : `around ${usd(cost)}`,
                "judged when each one ends",
              ]
                .filter((part) => part !== null)
                .join(" · ")}
        </span>
        <button type="button" className="sim-run" disabled={calling || total === 0 || (oneOnly && total !== 1) || tooMany} onClick={() => void run()}>
          <Icon name="play" size={14} />
          {calling ? "Starting…" : comparing ? `Compare ${String(against.length)} configurations${total > 1 ? ` × ${String(total)} callers` : ""}` : CHECKING ? "Run one call" : total === 0 ? "Run" : `Run ${String(total)} ${total === 1 ? "call" : "calls"}`}
        </button>
      </div>
    </section>
  );
}
