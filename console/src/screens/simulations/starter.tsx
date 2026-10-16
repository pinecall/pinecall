/** Starting a simulation: how the line is (spoken or written, how long, how noisy) and the callers to choose from — choosing one puts it on the agent and opens the call. */

import { useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Check, Chips, Input, Pill, Select, SelectItem } from "../../ui";
import { isPinecalls, type Persona } from "../personas/door";
import { Face } from "../personas/face";
import { startSimulation } from "./simulating";
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

type Line = "spoken" | "written";

const LINES: readonly { value: Line; label: string }[] = [
  { value: "spoken", label: "Spoken" },
  { value: "written", label: "Written" },
];

/**
 * The gateway plays the caller and calls the agent as anybody calls it, so whatever holds the agent
 * answers — the one deployed, or a `pinecall start` in its directory — and the call is judged at
 * hang-up like any other. A caller is started by choosing it: the call's id comes back at once and
 * the screen opens it.
 */
export function Starter({
  inView,
  agents,
  agent,
  onAgent,
  personas,
  asking,
  asked,
  all,
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
  /** The caller the page was opened for (Personas' "Use in a simulation"), marked in the grid. */
  asked?: string | undefined;
  /** Every caller is offered, the ones switched off too, as cards of their own under the enabled ones'. */
  all: boolean;
  /** Told the call's id the moment it has one, and whether it is on a spoken line. */
  onStarted: (call: string, spoken: boolean) => void;
}): ReactNode {
  const credentials = useCredentials();
  // The screen is for listening: a spoken line unless somebody wants a written one.
  const [line, setLine] = useState<Line>("spoken");
  const [turns, setTurns] = useState(TURNS);
  const [noisy, setNoisy] = useState(false);
  const [noise, setNoise] = useState(NOISE_DB);
  const [loss, setLoss] = useState(LOSS_PERCENT);
  const [background, setBackground] = useState<Background>("");
  const [calling, setCalling] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const spoken = line === "spoken";

  const start = async (persona: Persona): Promise<void> => {
    if (calling !== null) return;
    setCalling(persona.name);
    setRefused(null);
    try {
      // An agent's own caller rings the agent it was written for; Pinecall's ring the one picked.
      const call = await startSimulation(credentials, {
        agent: isPinecalls(persona) || inView !== "" ? agent : persona.agent,
        persona: persona.name,
        voice: spoken,
        turns,
        ...(spoken && noisy ? { interferer_db: noise, packet_loss: loss / 100, ...(background === "" ? {} : { ambience: background }) } : {}),
      });
      onStarted(call, spoken);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      setCalling(null);
    }
  };

  return (
    <section className="ui-tiles-block" aria-label="new simulation">
      <div className="sim-bar">
        <Chips options={LINES} value={line} onChange={setLine} />
        <label className="sim-turns">
          <Input size="sm" type="number" aria-label="Turns the caller says" min={1} max={30} value={turns} onChange={(event) => setTurns(Number(event.target.value))} />
          <span>turns</span>
        </label>
        {spoken && (
          <Check checked={noisy} onChange={setNoisy}>
            Noisy line
          </Check>
        )}
        {spoken && noisy && (
          <>
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
          </>
        )}
      </div>
      {refused !== null && <p className="sim-refused">{refused}</p>}
      {agents.length === 0 && <p className="sim-note">No agent is running in this world: deploy one, or run pinecall start in its directory.</p>}
      {personas === null && asking !== null && <p className="sim-note">{asking}</p>}
      {personas !== null && personas.length === 0 && <p className="sim-note">No personas yet: write the first caller in Personas.</p>}
      {personas !== null && inView === "" ? (
        <Everyones personas={personas} agents={agents} agent={agent} onAgent={onAgent} asked={asked} calling={calling} onChoose={(persona) => void start(persona)} />
      ) : (
        personas !== null && (
          <>
            {enabled(personas).length > 0 && (
              <>
                <p className="sim-prompt">Ready to call {agent}</p>
                <div className="ui-tiles">
                  {enabled(personas).map((persona) => (
                    <CallerTile key={persona.name} persona={persona} asked={persona.name === asked} calling={calling} onChoose={() => void start(persona)} />
                  ))}
                </div>
              </>
            )}
            {(all || enabled(personas).length === 0) && switchedOff(personas).length > 0 && (
              <>
                <p className="sim-prompt">{enabled(personas).length === 0 ? `Pinecall's callers · none is switched on for ${agent} yet, and any of them can still call it` : `Switched off for ${agent} · called by hand`}</p>
                <div className="ui-tiles">
                  {switchedOff(personas).map((persona) => (
                    <CallerTile key={persona.name} persona={persona} asked={persona.name === asked} calling={calling} onChoose={() => void start(persona)} />
                  ))}
                </div>
              </>
            )}
          </>
        )
      )}
    </section>
  );
}

/**
 * Every agent in view: every agent's own callers, each under its agent and ringing it, then
 * Pinecall's library once, ringing the agent picked beside its heading. Nothing is filtered: who is
 * in view is the sidebar's to narrow.
 */
function Everyones({
  personas,
  agents,
  agent,
  onAgent,
  asked,
  calling,
  onChoose,
}: {
  personas: Persona[];
  agents: readonly string[];
  agent: string;
  onAgent: (agent: string) => void;
  asked: string | undefined;
  calling: string | null;
  onChoose: (persona: Persona) => void;
}): ReactNode {
  const own = personas.filter((persona) => !isPinecalls(persona));
  const library = inOrder(personas.filter(isPinecalls));
  return (
    <>
      {own.length > 0 && (
        <>
          <p className="sim-prompt">Written for your agents · each rings its own</p>
          <div className="ui-tiles">
            {own.map((persona) => (
              <CallerTile key={`${persona.agent}/${persona.name}`} persona={persona} rings={persona.agent} asked={persona.name === asked} calling={calling} onChoose={() => onChoose(persona)} />
            ))}
          </div>
        </>
      )}
      {library.length > 0 && (
        <>
          <div className="sim-prompt sim-prompt-pick">
            <span>Pinecall's callers · ring</span>
            {agents.length > 1 ? (
              <Select size="sm" value={agent} onValueChange={onAgent} aria-label="The agent Pinecall's callers ring">
                {agents.map((one) => (
                  <SelectItem key={one} value={one}>
                    {one}
                  </SelectItem>
                ))}
              </Select>
            ) : (
              <span>{agent}</span>
            )}
          </div>
          <div className="ui-tiles">
            {library.map((persona) => (
              <CallerTile key={persona.name} persona={persona} asked={persona.name === asked} calling={calling} onChoose={() => onChoose(persona)} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

// The callers a person has enabled: the ones written for the agent, and Pinecall's it switched on.
function enabled(personas: Persona[]): Persona[] {
  return inOrder(personas).filter(isOn);
}

// Pinecall's callers the agent has switched off: its nightly plays none of them, a person may.
function switchedOff(personas: Persona[]): Persona[] {
  return inOrder(personas).filter((persona) => !isOn(persona));
}

function isOn(persona: Persona): boolean {
  return !isPinecalls(persona) || persona.on;
}

function CallerTile({ persona, rings, asked, calling, onChoose }: { persona: Persona; rings?: string; asked: boolean; calling: string | null; onChoose: () => void }): ReactNode {
  const library = isPinecalls(persona);
  const acts = [
    persona.behavior.interrupts > 0 ? `talks over ${Math.round(persona.behavior.interrupts * 100)}%` : null,
    persona.behavior.pause_s > 0 ? `pauses ${persona.behavior.pause_s}s` : null,
  ].filter((one): one is string => one !== null);
  const about = library ? (persona.summary ?? "") : persona.about;
  const classes = ["ui-tile", "sim-tile", isOn(persona) ? null : "ui-tile-off sim-tile-off", asked ? "sim-tile-asked" : null];
  return (
    <article className={classes.filter((one) => one !== null).join(" ")}>
      <button type="button" className="ui-tile-open" aria-label={`Call as ${persona.name}`} disabled={calling !== null} onClick={onChoose} />
      <div className="ui-tile-top">
        <Face name={persona.name} size={64} />
        {library ? (
          <Pill tone="gray" small>
            {persona.on ? "Pinecall" : "Pinecall · off"}
          </Pill>
        ) : (
          <Pill tone="violet" small>
            yours
          </Pill>
        )}
      </div>
      <h3 className="ui-tile-name">{persona.name}</h3>
      {about !== "" && <p className="sim-tile-about">{about}</p>}
      {persona.goal !== "" && persona.goal !== about && (
        <p className="sim-tile-goal">
          <span>Wants</span> {persona.goal}
        </p>
      )}
      <div className="ui-tile-tags">
        {rings !== undefined && (
          <Pill tone="indigo" small>
            rings {rings}
          </Pill>
        )}
        {persona.tags.map((tag) => (
          <Pill key={tag} tone={tag === "red-team" ? "red" : "gray"} small>
            {tag}
          </Pill>
        ))}
      </div>
      <footer className="ui-tile-foot">
        <span>{calling === persona.name ? "Calling…" : acts.length === 0 ? "calm on the line" : acts.join(" · ")}</span>
        <span>{calling === persona.name ? "" : "Call as them →"}</span>
      </footer>
    </article>
  );
}

// Every caller, the ones switched off for the nightly too: any of Pinecall's may be called by hand.
// The agent's own first, the ones somebody wrote for it; Pinecall's library after them, realism
// before the red team.
function inOrder(personas: Persona[]): Persona[] {
  const own = personas.filter((persona) => !isPinecalls(persona));
  const red = (persona: Persona): number => Number(persona.tags.includes("red-team"));
  const library = personas.filter(isPinecalls).sort((one, other) => red(one) - red(other) || one.name.localeCompare(other.name));
  return [...own, ...library];
}
