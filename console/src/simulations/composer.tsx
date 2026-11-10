/** A new simulation: which agent, who calls, how they call and for how long; each caller ticked is a call of its own, or, comparing, a task every model picked is put to. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { money } from "../lib/format";
import { Icon, type IconName } from "../shell/icons";
import { Select } from "../ui/select";
import { Callers } from "./callers";
import { readCallers, readLimits, readModels, setupKey, STAGES, startComparison, startSimulation, USUAL_LIMITS, type AgentValues, type Limits, type Modality, type Models, type Persona } from "./door";
import { askedBy, HowTheyCall, USUAL_HOW, type How } from "./how";

// A stage a setup leaves alone: the agent's own, the one to beat.
const AS_IT_IS = "";
// How many times each task is put to each setup: once tells whether it can, more how often it does.
const REPEATS: readonly number[] = [1, 3, 5];

const DOINGS: readonly { comparing: boolean; icon: IconName; title: string }[] = [
  { comparing: false, icon: "simulations", title: "Run callers" },
  { comparing: true, icon: "judges", title: "Compare setups" },
];

/** An agent a caller may ring, and which page holds it: Agents for one made in Studio, Apps for one written as code. */
export interface Rung {
  slug: string;
  kind: "class" | "studio";
}

/** What a call of these has taken and cost so far, read off the ones already made. */
export interface Typical {
  seconds: number | null;
  usd: number | null;
}

export function Composer({ agents, asked, askedCaller = null, typical, onStarted, onCompared }: { agents: readonly Rung[]; asked: string | null; askedCaller?: string | null; typical: Typical; onStarted: (calls: string[]) => void; onCompared: (comparison: string) => void }): ReactNode {
  const credentials = useCredentials();
  const homes = new Map(agents.map((one) => [one.slug, one.kind === "studio" ? "/agents" : "/apps"]));
  const [agent, setAgent] = useState(asked !== null && homes.has(asked) ? asked : (agents[0]?.slug ?? ""));
  const [callers, setCallers] = useState<Persona[] | null>(null);
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const [how, setHow] = useState<How>(USUAL_HOW);
  const [comparing, setComparing] = useState(false);
  const [models, setModels] = useState<Models | null>(null);
  const [setups, setSetups] = useState<readonly AgentValues[]>([{}, {}]);
  const [repeats, setRepeats] = useState(1);
  const [limits, setLimits] = useState<Limits>(USUAL_LIMITS);

  // What the org may place is its own: a gateway from before it said so answers nothing, and the platform's stand.
  useEffect(() => {
    let gone = false;
    readLimits(credentials).then(
      (read) => !gone && setLimits(read),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  // The agents are read after the page is drawn: the first one is taken once they are.
  useEffect(() => {
    if (agent === "" && agents[0] !== undefined) setAgent(agents[0].slug);
  }, [agent, agents]);

  // Another agent has other callers: what was ticked for the last one is not carried over.
  useEffect(() => {
    if (agent === "") return;
    let gone = false;
    setCallers(null);
    setPicked(new Set());
    setRefused(null);
    readCallers(credentials, agent).then(
      (read) => {
        if (gone) return;
        setCallers(read);
        // A link from Personas names the caller to ring with: it starts ticked, for the agent it was asked of.
        if (askedCaller !== null && agent === asked && read.some((one) => one.name === askedCaller)) setPicked(new Set([askedCaller]));
      },
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
    setSetups([{}, {}]);
    readModels(credentials, agent).then(
      (read) => !gone && setModels(read),
      (failed) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, comparing]);

  const pick = (name: string): void => {
    const next = new Set(picked);
    if (!next.delete(name)) next.add(name);
    setPicked(next);
  };

  const run = async (): Promise<void> => {
    if (starting || picked.size === 0) return;
    setStarting(true);
    setRefused(null);
    if (comparing) {
      await compare();
      return;
    }
    const calls: string[] = [];
    try {
      for (const persona of picked) {
        calls.push(await startSimulation(credentials, { agent, persona, ...askedBy(how) }));
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
  const compare = async (): Promise<void> => {
    const [first, ...more] = [...picked];
    if (first === undefined) return;
    try {
      const placed = await startComparison(credentials, { agent, persona: first, more_personas: more, ...askedBy(how), against: [...setups], repeats });
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
      <div className="app-open-note">
        <div className="app-empty">
          <h2 className="app-name">No agent is running</h2>
          <p className="dash-quiet">A simulated caller rings an agent that is running. Start one from its project, or create one in Agents, and its callers show up here.</p>
          <code className="app-command">pinecall start</code>
        </div>
      </div>
    );
  }

  const count = comparing ? picked.size * setups.length * repeats : picked.size;
  const tooMany = comparing && count > limits.comparison_calls;
  // Two columns that run the agent on the same thing would compare it with itself.
  const twice = new Set(setups.map(setupKey)).size < setups.length;
  const ready = picked.size > 0 && (!comparing || (setups.length >= 2 && !tooMany && !twice));
  const setStage = (at: number, modality: Modality, word: string): void =>
    setSetups(
      setups.map((setup, index) => {
        if (index !== at) return setup;
        const rest: AgentValues = { ...setup };
        delete rest[modality];
        return word === AS_IT_IS ? rest : { ...rest, [modality]: word };
      }),
    );
  const minutes = typical.seconds === null ? null : Math.max(1, Math.round(typical.seconds / 60));
  const placing = comparing ? `${picked.size} ${picked.size === 1 ? "task" : "tasks"} × ${setups.length} setups${repeats > 1 ? ` × ${repeats} times` : ""} = ${count} calls` : `${count} ${count === 1 ? "call" : "calls"}`;
  const foot = [
    picked.size === 0 ? (comparing ? "Pick the tasks" : "Pick who calls") : placing,
    comparing && twice ? "two setups are the same" : null,
    tooMany ? `this org places ${limits.comparison_calls} calls a comparison at most: fewer tasks, setups or repeats` : null,
    comparing && !tooMany && count > limits.at_once ? `${limits.at_once} at once, the rest wait their turn` : null,
    !comparing && count > limits.at_once ? `${limits.at_once} at once at most` : null,
    picked.size > 0 && minutes !== null ? `about ${minutes} min each` : null,
    picked.size > 0 && typical.usd !== null ? `around ${money(typical.usd * count)}` : null,
    picked.size > 0 ? "judged at hang-up" : null,
  ].filter((part) => part !== null);

  return (
    <>
      <nav className="app-tabs" aria-label="What to run">
        {DOINGS.map((one) => (
          <button key={one.title} type="button" aria-pressed={comparing === one.comparing} className={comparing === one.comparing ? "app-tab app-tab-on sim-tab" : "app-tab sim-tab"} onClick={() => setComparing(one.comparing)}>
            <Icon name={one.icon} size={15} />
            {one.title}
          </button>
        ))}
      </nav>
      <div className="app-main">
        <p className="dash-quiet app-note">{comparing ? "The same tasks on several setups of the agent, a model, an ear, a voice: which gets them done, how often, how fast, and for how much." : "Pretend callers ring your agent before real ones do. Every call is judged when it ends."}</p>

        <section className="dash-card" aria-label={comparing ? "Tasks" : "Who calls"}>
          <div className="dash-card-top">
            <span className="dash-eyebrow">{comparing ? "Tasks" : "Who calls"}</span>
            <span className="sim-top-right">
              {agent !== "" && (
                <Link to={`${homes.get(agent) ?? "/agents"}/${encodeURIComponent(agent)}/test`} className="dash-more">
                  Edit callers
                </Link>
              )}
              {agents.length > 1 && (
                <span className="sim-pick">
                  <Select label="The agent they ring" value={agent} items={agents.map((one) => ({ value: one.slug, label: one.slug }))} onChange={setAgent} />
                </span>
              )}
            </span>
          </div>
          {comparing && <p className="dash-quiet sim-hint">Each caller is a task: it phones wanting one thing, and its call is judged on whether the agent got it done. Write one caller per thing your agent must do, a booking, a change, a cancellation, each with what it expects.</p>}
          {callers === null && <p className="dash-quiet">Reading the callers…</p>}
          {callers !== null && callers.length === 0 && refused === null && <p className="dash-quiet">This agent has no caller yet. Write the first one in its Test tab.</p>}
          {callers !== null && callers.length > 0 && <Callers callers={callers} picked={picked} onPick={pick} goals={comparing} />}
        </section>

        {comparing && (
          <section className="dash-card" aria-label="Setups">
            <div className="dash-card-top">
              <span className="dash-eyebrow">Setups</span>
              <span className="sim-top-right">
                <span className="dash-quiet">Each task, on each setup</span>
                <div className="dash-switch" role="group" aria-label="How many times">
                  {REPEATS.map((times) => (
                    <button key={times} type="button" aria-pressed={repeats === times} className={repeats === times ? "dash-switch-on" : ""} onClick={() => setRepeats(times)}>
                      {times === 1 ? "Once" : `${times} times`}
                    </button>
                  ))}
                </div>
              </span>
            </div>
            {models === null ? (
              <p className="dash-quiet">Reading the models…</p>
            ) : (
              <div className="sim-setups">
                <div className="sim-setup sim-setup-head">
                  <span />
                  {STAGES.map((stage) => (
                    <span key={stage.modality} className="dash-quiet">
                      {stage.name}
                    </span>
                  ))}
                  <span />
                </div>
                {setups.map((setup, at) => (
                  <div key={at} className="sim-setup">
                    <span className="sim-setup-n">{at + 1}</span>
                    {STAGES.map((stage) => (
                      <Select
                        key={stage.modality}
                        label={`Setup ${at + 1}: ${stage.name.toLowerCase()} with`}
                        value={setup[stage.modality] ?? AS_IT_IS}
                        items={[
                          { value: AS_IT_IS, label: "Same as the agent", detail: models.own[stage.modality] },
                          ...models.offered[stage.modality].map((one) => ({ value: one.value, label: one.name, group: one.vendor, keywords: one.value, disabled: !one.available, hint: one.available ? undefined : "This org has no key for this vendor", tags: one.recommended ? <span className="ui-badge">Recommended</span> : undefined })),
                        ]}
                        onChange={(word) => setStage(at, stage.modality, word)}
                      />
                    ))}
                    <button type="button" className="sim-setup-drop" aria-label={`Remove setup ${at + 1}`} disabled={setups.length <= 2} onClick={() => setSetups(setups.filter((_, index) => index !== at))}>
                      <Icon name="close" size={13} />
                    </button>
                  </div>
                ))}
                <button type="button" className="app-button sim-setup-add" onClick={() => setSetups([...setups, {}])}>
                  Add a setup
                </button>
              </div>
            )}
          </section>
        )}

        <HowTheyCall title="How they call" how={how} onChange={setHow} />

        {refused !== null && <p className="app-refused">{refused}</p>}
        <footer className="sim-foot">
          <span className="dash-quiet">{foot.join(" · ")}</span>
          <button type="button" className="sim-run" disabled={starting || !ready} onClick={() => void run()}>
            {starting ? "Starting…" : comparing ? "Compare" : count <= 1 ? "Run call" : `Run ${count} calls`}
          </button>
        </footer>
      </div>
    </>
  );
}
