/** A new simulation: which agent, who calls, how they call and for how long; each caller ticked is a call of its own, or, comparing, a task every model picked is put to. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { money } from "../lib/format";
import { WORLD } from "../lib/world";
import { Icon, type IconName } from "../shell/icons";
import { Select } from "../ui/select";
import { Callers } from "./callers";
import { COMPARED_AT_MOST, readCallers, readModels, startComparison, startSimulation, type Ambience, type Line, type Models, type Persona, type Wanted } from "./door";

const LINES: readonly { value: Line; icon: IconName; title: string; about: string }[] = [
  { value: "chat", icon: "chat", title: "Chat", about: "Typed. The fastest, and it uses no call minutes." },
  { value: "call", icon: "numbers", title: "Phone call", about: "Spoken out loud, on a clear line." },
  { value: "noisy", icon: "speaker", title: "Noisy call", about: "Spoken, with a room behind the caller the whole call." },
];

// "" is the caller's own room: what its persona says, a television when it says nothing.
const ROOMS: readonly { value: Ambience | ""; title: string; about: string }[] = [
  { value: "", title: "Caller's own", about: "What the caller is set to" },
  { value: "cafe", title: "Café", about: "Tables talking at once" },
  { value: "street", title: "Street", about: "Traffic, rising and fading" },
  { value: "office", title: "Office", about: "A steady hum" },
  { value: "television", title: "Television", about: "One voice competing" },
];

// The turns a caller improvises before it hangs up.
const LENGTHS: readonly { turns: number; name: string }[] = [
  { turns: 6, name: "Short" },
  { turns: 15, name: "Normal" },
  { turns: 30, name: "Long" },
];

// The room's level is dB under the caller's voice: fewer is louder. The slider reads the other way, as a volume does.
const FAINTEST_DB = 30;
const LOUDEST_DB = 5;
const USUAL_DB = 15;
// The gateway holds an org to this many simulated calls on the line at once.
const AT_ONCE = 10;
// Production takes one caller, one call: a check of the agent as it is deployed.
const CHECKING = WORLD === "production";
// A column of a comparison that names no model: the agent on its own settings, the one to beat.
const AS_IT_IS = "";

const DOINGS: readonly { comparing: boolean; icon: IconName; title: string; about: string }[] = [
  { comparing: false, icon: "simulations", title: "Run callers", about: "Each caller rings the agent as it is." },
  { comparing: true, icon: "judges", title: "Compare models", about: "The same tasks on several models: which gets them done, how fast, for how much." },
];

/** What a call of these has taken and cost so far, read off the ones already made. */
export interface Typical {
  seconds: number | null;
  usd: number | null;
}

function loudness(db: number): string {
  if (db <= 9) return "Loud";
  if (db <= 19) return "Clearly there";
  return "Faint";
}

export function Composer({ agents, asked, typical, onStarted, onCompared }: { agents: readonly string[]; asked: string | null; typical: Typical; onStarted: (calls: string[]) => void; onCompared: (comparison: string) => void }): ReactNode {
  const credentials = useCredentials();
  const [agent, setAgent] = useState(asked !== null && agents.includes(asked) ? asked : (agents[0] ?? ""));
  const [callers, setCallers] = useState<Persona[] | null>(null);
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const [line, setLine] = useState<Line>("call");
  const [room, setRoom] = useState<Ambience | "">("cafe");
  const [db, setDb] = useState(USUAL_DB);
  const [loss, setLoss] = useState(0);
  const [turns, setTurns] = useState(15);
  const [comparing, setComparing] = useState(false);
  const [models, setModels] = useState<Models | null>(null);
  const [setups, setSetups] = useState<readonly string[]>([AS_IT_IS]);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  // The agents are read after the page is drawn: the first one is taken once they are.
  useEffect(() => {
    if (agent === "" && agents[0] !== undefined) setAgent(agents[0]);
  }, [agent, agents]);

  // Another agent has other callers: what was ticked for the last one is not carried over.
  useEffect(() => {
    if (agent === "") return;
    let gone = false;
    setCallers(null);
    setPicked(new Set());
    setRefused(null);
    readCallers(credentials, agent).then(
      (read) => !gone && setCallers(read),
      (failed) => {
        if (gone) return;
        setCallers([]);
        setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  // The models are asked for once somebody compares: a run of callers needs none of them.
  useEffect(() => {
    if (!comparing || agent === "") return;
    let gone = false;
    setModels(null);
    setSetups([AS_IT_IS]);
    readModels(credentials, agent).then(
      (read) => !gone && setModels(read),
      (failed) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, comparing]);

  const pick = (name: string): void => {
    if (CHECKING) {
      setPicked(new Set([name]));
      return;
    }
    const next = new Set(picked);
    if (!next.delete(name)) next.add(name);
    setPicked(next);
  };

  const run = async (): Promise<void> => {
    if (starting || picked.size === 0) return;
    setStarting(true);
    setRefused(null);
    const noise = line === "noisy" ? { interferer_db: db, packet_loss: loss / 100, ...(room === "" ? {} : { ambience: room }) } : {};
    if (comparing) {
      await compare(noise);
      return;
    }
    const calls: string[] = [];
    try {
      for (const persona of picked) {
        const wanted: Wanted = { agent, persona, voice: line !== "chat", turns, ...noise };
        calls.push(await startSimulation(credentials, wanted));
      }
    } catch (failed) {
      // What had started stays started: the page carries on with those.
      setRefused(calls.length === 0 ? saidBy(failed) : `${saidBy(failed)} ${calls.length} of ${picked.size} started.`);
    } finally {
      setStarting(false);
    }
    if (calls.length > 0) onStarted(calls);
  };

  // One call per task and model, placed together; what the gateway refused of them is said, and the rest are the board.
  const compare = async (noise: Partial<Wanted>): Promise<void> => {
    const [first, ...more] = [...picked];
    if (first === undefined) return;
    try {
      const placed = await startComparison(credentials, { agent, persona: first, more_personas: more, voice: line !== "chat", turns, ...noise, against: setups.map((model) => (model === AS_IT_IS ? {} : { llm: model })) });
      if (placed.calls.length > 0) onCompared(placed.comparison);
      else setRefused(placed.refused.map((one) => one.why).join(" · "));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setStarting(false);
    }
  };

  if (agents.length === 0) {
    return (
      <div className="app-empty">
        <h2 className="app-name">No agent is running</h2>
        <p className="dash-quiet">A simulated caller rings an agent that is running. Start one from its project, or create one in Agents, and its callers show up here.</p>
        <code className="app-command">pinecall start</code>
      </div>
    );
  }

  const count = comparing ? picked.size * setups.length : picked.size;
  const tooMany = comparing && count > COMPARED_AT_MOST;
  const ready = picked.size > 0 && (!comparing || (setups.length >= 2 && !tooMany));
  const minutes = typical.seconds === null ? null : Math.max(1, Math.round(typical.seconds / 60));
  const foot = [picked.size === 0 ? (CHECKING ? "Pick one caller" : comparing ? "Pick the tasks" : "Pick who calls") : comparing ? `${picked.size} ${picked.size === 1 ? "task" : "tasks"} × ${setups.length} ${setups.length === 1 ? "model" : "models"} = ${count} calls` : `${count} ${count === 1 ? "call" : "calls"}`, comparing && setups.length < 2 ? "add a model to compare with" : null, tooMany ? `${COMPARED_AT_MOST} calls at most: fewer tasks or models` : null, !comparing && count > AT_ONCE ? `${AT_ONCE} at once at most` : null, picked.size > 0 && minutes !== null ? `about ${minutes} min each` : null, picked.size > 0 && typical.usd !== null ? `around ${money(typical.usd * count)}` : null, picked.size > 0 ? "judged at hang-up" : null].filter((part) => part !== null);

  return (
    <section className="dash-card sim-new" aria-label="New simulation">
      <header className="sim-new-head">
        <h2 className="app-name">{CHECKING ? "Check call" : "New simulation"}</h2>
        <p className="dash-quiet">{CHECKING ? "One pretend caller rings the agent as it is deployed, on production's own keys and knowledge." : "Pretend callers ring your agent before real ones do. Every call is judged when it ends."}</p>
      </header>

      {!CHECKING && (
        <div className="sim-ways sim-doings" role="radiogroup" aria-label="What to run">
          {DOINGS.map((one) => (
            <button key={one.title} type="button" role="radio" aria-checked={comparing === one.comparing} className={comparing === one.comparing ? "sim-way sim-way-on" : "sim-way"} onClick={() => setComparing(one.comparing)}>
              <span className="sim-way-icon">
                <Icon name={one.icon} size={16} />
              </span>
              <span className="sim-way-title">{one.title}</span>
              <span className="sim-way-about">{one.about}</span>
            </button>
          ))}
        </div>
      )}

      {agents.length > 1 && (
        <div className="sim-step">
          <span className="sim-step-name">Agent</span>
          <div className="sim-agent">
            <Select label="The agent they ring" value={agent} items={agents.map((one) => ({ value: one, label: one }))} onChange={setAgent} />
          </div>
        </div>
      )}

      <div className="sim-step">
        <span className="sim-step-name">
          {comparing ? "Tasks" : "Who calls"}
          <Link to="/personas" className="sim-link">
            Edit callers
          </Link>
        </span>
        {comparing && <p className="dash-quiet sim-hint">Each caller is a task: it phones wanting one thing, and its call is judged on whether the agent got it done. Write one caller per thing your agent must do, a booking, a change, a cancellation, each with what it expects.</p>}
        {callers === null && <p className="dash-quiet">Reading the callers…</p>}
        {callers !== null && callers.length === 0 && refused === null && <p className="dash-quiet">This agent has no caller yet. Write the first one in Personas.</p>}
        {callers !== null && callers.length > 0 && <Callers callers={callers} picked={picked} onPick={pick} one={CHECKING} goals={comparing} />}
      </div>

      {comparing && (
        <div className="sim-step">
          <span className="sim-step-name">Models</span>
          {models === null ? (
            <p className="dash-quiet">Reading the models…</p>
          ) : (
            <>
              <div className="sim-setups">
                {setups.map((model, at) => (
                  <span key={model} className="sim-setup">
                    <span className="sim-setup-n">{at + 1}</span>
                    <span className="sim-setup-words">
                      <span className="dash-clip">{model === AS_IT_IS ? "The agent as it is" : (models.offered.find((one) => one.value === model)?.name ?? model)}</span>
                      <span className="sim-setup-under dash-clip">{model === AS_IT_IS ? models.own : model.slice(0, model.indexOf("/"))}</span>
                    </span>
                    <button type="button" className="sim-setup-drop" aria-label="Remove" onClick={() => setSetups(setups.filter((one) => one !== model))}>
                      <Icon name="close" size={13} />
                    </button>
                  </span>
                ))}
              </div>
              <div className="sim-agent">
                <Select
                  label="Add a model to compare"
                  placeholder="Add a model…"
                  value=""
                  items={[...(setups.includes(AS_IT_IS) ? [] : [{ value: AS_IT_IS, label: "The agent as it is", detail: models.own }]), ...models.offered.filter((one) => !setups.includes(one.value)).map((one) => ({ value: one.value, label: one.name, group: one.vendor, keywords: one.value, disabled: !one.available, hint: one.available ? undefined : "This org has no key for this vendor", tags: one.recommended ? <span className="ui-badge">Recommended</span> : undefined }))]}
                  onChange={(model) => setSetups([...setups, model])}
                />
              </div>
            </>
          )}
        </div>
      )}

      <div className="sim-step">
        <span className="sim-step-name">How they call</span>
        <div className="sim-ways" role="radiogroup" aria-label="How they call">
          {LINES.map((one) => (
            <button key={one.value} type="button" role="radio" aria-checked={line === one.value} className={line === one.value ? "sim-way sim-way-on" : "sim-way"} onClick={() => setLine(one.value)}>
              <span className="sim-way-icon">
                <Icon name={one.icon} size={16} />
              </span>
              <span className="sim-way-title">{one.title}</span>
              <span className="sim-way-about">{one.about}</span>
            </button>
          ))}
        </div>
        {line === "noisy" && (
          <div className="sim-noise">
            <div className="sim-rooms" role="radiogroup" aria-label="What plays behind the caller">
              {ROOMS.map((one) => (
                <button key={one.value} type="button" role="radio" aria-checked={room === one.value} className={room === one.value ? "sim-room sim-room-on" : "sim-room"} onClick={() => setRoom(one.value)}>
                  <span className="sim-room-title">{one.title}</span>
                  <span className="sim-room-about">{one.about}</span>
                </button>
              ))}
            </div>
            <label className="sim-level">
              <span className="sim-level-name">
                How loud
                <b>{loudness(db)}</b>
                <span className="dash-quiet">{db} dB under the voice</span>
              </span>
              <input type="range" aria-label="How loud the room is" min={0} max={FAINTEST_DB - LOUDEST_DB} step={1} value={FAINTEST_DB - db} onChange={(event) => setDb(FAINTEST_DB - Number(event.target.value))} />
            </label>
            <label className="sim-level">
              <span className="sim-level-name">
                Bad connection
                <b>{loss === 0 ? "None" : `${loss}% lost`}</b>
                <span className="dash-quiet">packets dropped off the line</span>
              </span>
              <input type="range" aria-label="Packets lost, percent" min={0} max={20} step={1} value={loss} onChange={(event) => setLoss(Number(event.target.value))} />
            </label>
          </div>
        )}
      </div>

      <div className="sim-step sim-step-row">
        <span className="sim-step-name">How long</span>
        <div className="dash-switch" role="group" aria-label="How long">
          {LENGTHS.map((one) => (
            <button key={one.turns} type="button" aria-pressed={turns === one.turns} className={turns === one.turns ? "dash-switch-on" : ""} onClick={() => setTurns(one.turns)}>
              {one.name}
            </button>
          ))}
        </div>
        <span className="dash-quiet">The caller says up to {turns} things, then hangs up.</span>
      </div>

      {refused !== null && <p className="app-refused">{refused}</p>}
      <footer className="sim-foot">
        <span className="dash-quiet">{foot.join(" · ")}</span>
        <button type="button" className="sim-run" disabled={starting || !ready} onClick={() => void run()}>
          {starting ? "Starting…" : comparing ? "Compare" : count <= 1 ? "Run call" : `Run ${count} calls`}
        </button>
      </footer>
    </section>
  );
}
