/** A caller in the side panel: who it is and how its last call went, the form that writes one, and the callers a model proposes for the agent. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { CallerBehavior } from "@pinecall/core/wire/rest-evals";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { ago, lengthOf } from "../lib/format";
import type { PersonaRun } from "../simulations/door";
import { Select } from "../ui/select";
import { Badge, Field, Fold, Setting } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { dropCaller, proposeCallers, switchCaller, writeCaller, type Persona, type PersonaPut, type ProposedPersona } from "./door";
import { aboutOf, isPinecalls, verdictOfCall } from "./fold";

// How a caller acts on a spoken line when nobody said otherwise.
const STILL: CallerBehavior = { interrupts: 0, pause_s: 0, interferer_db: null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "television" };
// The dB under the caller a background plays at when it is first picked.
const A_BACKGROUND_DB = 15;

type Choices = readonly { value: number; label: string }[];
const TALKS_OVER: Choices = [{ value: 0, label: "Never, waits for every answer" }, { value: 0.2, label: "Now and then, one answer in five" }, { value: 0.5, label: "Often, half the answers" }, { value: 0.8, label: "Almost always" }];
const PAUSES: Choices = [{ value: 0, label: "Answers at once" }, { value: 1.5, label: "A little, 1.5 s before each line" }, { value: 3, label: "Slow, 3 s, as someone thinking" }, { value: 6, label: "Very slow, 6 s" }];
const LOSSES: Choices = [{ value: 0, label: "A good line" }, { value: 0.02, label: "A few packets lost, 2%" }, { value: 0.1, label: "A bad line, 10% lost" }];
const SPEEDS: Choices = [{ value: 0.75, label: "Slow" }, { value: 0.9, label: "A little slower" }, { value: 1, label: "As the voice reads it" }, { value: 1.15, label: "A little faster" }, { value: 1.3, label: "Fast, in a hurry" }];
const BACKGROUNDS: readonly { value: string; label: string }[] = [{ value: "", label: "A quiet room" }, { value: "television", label: "A television" }, { value: "cafe", label: "A café" }, { value: "office", label: "An office" }, { value: "street", label: "A street" }];

/** A number picked among a few, the nearest standing for one the list does not have. */
function Among({ label, choices, value, onChange }: { label: string; choices: Choices; value: number; onChange: (value: number) => void }): ReactNode {
  const nearest = choices.reduce((best, one) => (Math.abs(one.value - value) < Math.abs(best.value - value) ? one : best));
  return <Select label={label} searchable={false} items={choices.map((one) => ({ value: String(one.value), label: one.label }))} value={String(nearest.value)} onChange={(picked) => onChange(Number(picked))} />;
}

/** How the caller behaves on a spoken line, in the few words that are not the default. */
function mannersOf(acts: CallerBehavior): string[] {
  return [
    ...(acts.interrupts > 0 ? [`Talks over ${Math.round(acts.interrupts * 100)}% of the answers`] : []),
    ...(acts.pause_s > 0 ? [`Waits ${acts.pause_s} s before each line`] : []),
    ...(acts.interferer_db !== null ? [`Calls with ${BACKGROUNDS.find((one) => one.value === acts.ambience)?.label.toLowerCase() ?? "noise"} behind`] : []),
    ...(acts.packet_loss > 0 ? [`On a line losing ${Math.round(acts.packet_loss * 100)}% of its packets`] : []),
    ...(acts.speed !== 1 ? [`Speaks at ${acts.speed}× the voice's pace`] : []),
  ];
}

function LastCall({ run }: { run: PersonaRun | undefined }): ReactNode {
  if (run === undefined) return <div className="tst-last">Never called. Start it in chat or by voice and it is judged when it hangs up.</div>;
  const verdict = run.ended_at === null ? "playing" : verdictOfCall(run);
  return (
    <div className={`tst-last tst-last-${verdict}`}>
      <span className="tst-last-top">
        <b>{verdict === "playing" ? "On the line now" : verdict === "none" ? "Not judged" : `${run.score?.held ?? 0} of ${run.score?.judged ?? 0} judges held`}</b>
        <span className="dash-quiet">
          {ago(run.started_at)}
          {run.ended_at !== null && `, ${lengthOf(run.started_at, run.ended_at)}`}
        </span>
      </span>
      {run.score?.reason != null && <p className="tst-last-why">{run.score.reason}</p>}
      <Link to={`/simulations/${run.call}`} className="tst-link">
        Open the call
      </Link>
    </div>
  );
}

/** One caller open. Pinecall's are taken into the agent or put back, never rewritten; the app's own code may own them all. */
export function CallerPanel({ agent, caller, last, starting, onStart, onEdit, onCallers, onClose }: { agent: string; caller: Persona; last: PersonaRun | undefined; starting: boolean; onStart: (voice: boolean) => void; onEdit: () => void; onCallers: (callers: Persona[], gone: boolean) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [refused, setRefused] = useState<string | null>(null);
  const library = isPinecalls(caller);
  const writable = caller.fixed !== true;
  const act = async (doing: () => Promise<Persona[]>, gone: boolean): Promise<void> => {
    setRefused(null);
    try {
      onCallers(await doing(), gone);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };
  const facts = Object.entries(caller.facts);
  const manners = mannersOf(caller.behavior);
  return (
    <SidePanel
      title={caller.name}
      icon="personas"
      about={aboutOf(caller)}
      actions={library ? <Badge quiet>Pinecall's</Badge> : undefined}
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            {writable && library && (
              <button type="button" className="app-button" onClick={() => void act(() => switchCaller(credentials, agent, caller.name, !caller.on), false)}>
                {caller.on ? "Take off this agent" : "Add to this agent"}
              </button>
            )}
            {writable && !library && <ConfirmButton label="Delete" asks="Delete this caller?" danger onConfirm={() => void act(() => dropCaller(credentials, agent, caller.name), true)} />}
            {writable && !library && (
              <button type="button" className="app-button" onClick={onEdit}>
                Edit
              </button>
            )}
            <button type="button" className="app-button" disabled={starting} onClick={() => onStart(true)}>
              Call by voice
            </button>
            <button type="button" className="cfg-save" disabled={starting} onClick={() => onStart(false)}>
              {starting ? "Starting…" : "Start in chat"}
            </button>
          </div>
        </>
      }
    >
      <LastCall run={last} />
      <Field label="What they want">
        <p className="tst-words">{caller.goal}</p>
      </Field>
      <Field label="How they talk">
        <p className="tst-words">{caller.style}</p>
        {manners.length > 0 && (
          <ul className="tst-demands">
            {manners.map((one) => (
              <li key={one} className="tst-demand">
                {one}
              </li>
            ))}
          </ul>
        )}
      </Field>
      {facts.length > 0 && (
        <Field label="What they know">
          <dl className="tst-facts">
            {facts.map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </Field>
      )}
      {caller.expects.length > 0 && (
        <Field label="What they expect of the agent">
          <ul className="tst-demands">
            {caller.expects.map((one) => (
              <li key={one} className="tst-demand tst-demand-must">
                {one}
              </li>
            ))}
          </ul>
        </Field>
      )}
      {caller.fixed === true && <p className="dash-quiet">Set in the app's code. Change it there and deploy.</p>}
    </SidePanel>
  );
}

const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** A caller written for the agent, or one of its own changed; what the form does not draw (its opening state, who plays it) goes back as it was. `among` asks whose it is in the form itself, on a page that shows several agents. */
export function CallerFormPanel({ agent, among, was, onSaved, onClose }: { agent: string; among?: readonly string[]; was: Persona | undefined; onSaved: (callers: Persona[], name: string, agent: string) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [whose, setWhose] = useState(agent);
  const [name, setName] = useState(was?.name ?? "");
  const [about, setAbout] = useState(was?.about ?? "");
  const [goal, setGoal] = useState(was?.goal ?? "");
  const [style, setStyle] = useState(was?.style ?? "");
  const [facts, setFacts] = useState<[string, string][]>(() => [...Object.entries(was?.facts ?? {}), ["", ""]]);
  const [expects, setExpects] = useState((was?.expects ?? []).join("\n"));
  const [acts, setActs] = useState<CallerBehavior>(was?.behavior ?? STILL);
  const [advanced, setAdvanced] = useState(was !== undefined && mannersOf(was.behavior).length > 0);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const behave = (change: Partial<CallerBehavior>): void => setActs((held) => ({ ...held, ...change }));

  // A fact row typed into grows the list by one, so there is always an empty one to write the next in.
  const setFact = (at: number, row: [string, string]): void => {
    const next = facts.map((one, index) => (index === at ? row : one));
    setFacts(next.at(-1)?.some((part) => part !== "") === true ? [...next, ["", ""]] : next);
  };

  const save = async (): Promise<void> => {
    const called = name.trim();
    if (!A_NAME.test(called)) return setRefused("Name it in lowercase words joined by dashes: angry-about-a-bill.");
    if (goal.trim() === "" || style.trim() === "") return setRefused("Say what they want and how they talk.");
    const body: PersonaPut = {
      about: about.trim(),
      goal: goal.trim(),
      style: style.trim(),
      facts: Object.fromEntries(facts.filter(([what]) => what.trim() !== "").map(([what, said]) => [what.trim(), said.trim()])),
      expects: expects.split("\n").map((line) => line.trim()).filter((line) => line !== ""),
      behavior: acts,
      state: was?.state ?? {},
      llm: was?.llm ?? null,
      tts: was?.tts ?? null,
      voice: was?.voice ?? null,
      tags: was?.tags ?? [],
      ...(was === undefined || was.name === called ? {} : { was: was.name }),
    };
    setSaving(true);
    setRefused(null);
    try {
      onSaved(await writeCaller(credentials, whose, called, body), called, whose);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EditDialog title={was === undefined ? "New caller" : `Edit ${was.name}`} icon="personas" about="Somebody who phones the agent: what they want, how they talk and what they know. A model plays them, in chat or out loud." saving={saving} refused={refused} onSave={() => void save()} onClose={onClose}>
      {among !== undefined && (
        <Field label="Which agent">
          <Select label="Which agent" value={whose} items={among.map((slug) => ({ value: slug, label: slug }))} onChange={setWhose} />
        </Field>
      )}
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="angry-about-a-bill" spellCheck={false} value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field label="In a line">
        <input className="cfg-input" aria-label="In a line" placeholder="A customer charged twice last month" value={about} onChange={(event) => setAbout(event.target.value)} />
      </Field>
      <Field label="What they want">
        <textarea className="cfg-input cfg-area" aria-label="What they want" rows={3} placeholder="I was charged twice for October and I want one charge refunded today." value={goal} onChange={(event) => setGoal(event.target.value)} />
      </Field>
      <Field label="How they talk">
        <textarea className="cfg-input cfg-area" aria-label="How they talk" rows={2} placeholder="Short sentences, impatient, repeats the amount." value={style} onChange={(event) => setStyle(event.target.value)} />
      </Field>
      <Field label="What they know">
        <div className="tst-fact-rows">
          {facts.map(([what, said], at) => (
            <div key={at} className="tst-fact-row">
              <input className="cfg-input" aria-label="Fact" placeholder="account" spellCheck={false} value={what} onChange={(event) => setFact(at, [event.target.value, said])} />
              <input className="cfg-input" aria-label="Its value" placeholder="88213" value={said} onChange={(event) => setFact(at, [what, event.target.value])} />
            </div>
          ))}
        </div>
        <span className="tst-hint">What they answer when the agent asks: a name, a date of birth, an order number.</span>
      </Field>
      <Field label="What they expect of the agent">
        <textarea className="cfg-input cfg-area" aria-label="What they expect of the agent" rows={3} placeholder={"The agent offers a refund or a person.\nThe agent never asks for the card number."} value={expects} onChange={(event) => setExpects(event.target.value)} />
        <span className="tst-hint">One a line. A judge reads the call against each when it hangs up.</span>
      </Field>
      <Fold title="On a spoken line" open={advanced} onToggle={() => setAdvanced((was_) => !was_)} />
      {advanced && (
        <>
          <Setting icon="bolt" title="Talks over the agent" about="How often they start speaking before an answer ends.">
            <Among label="Talks over the agent" choices={TALKS_OVER} value={acts.interrupts} onChange={(interrupts) => behave({ interrupts })} />
          </Setting>
          <Setting icon="clock" title="Takes their time" about="Silence before each of their lines.">
            <Among label="Takes their time" choices={PAUSES} value={acts.pause_s} onChange={(pause_s) => behave({ pause_s })} />
          </Setting>
          <Setting icon="speaker" title="Behind them" about="What plays in the room they call from.">
            <Select label="Behind them" searchable={false} items={BACKGROUNDS} value={acts.interferer_db === null ? "" : acts.ambience} onChange={(picked) => behave(picked === "" ? { interferer_db: null } : { ambience: picked as CallerBehavior["ambience"], interferer_db: acts.interferer_db ?? A_BACKGROUND_DB })} />
          </Setting>
          <Setting icon="gauge" title="The line" about="How much of what they say is lost on the way.">
            <Among label="The line" choices={LOSSES} value={acts.packet_loss} onChange={(packet_loss) => behave({ packet_loss })} />
          </Setting>
          <Setting icon="type" title="Pace" about="How fast they speak.">
            <Among label="Pace" choices={SPEEDS} value={acts.speed} onChange={(speed) => behave({ speed })} />
          </Setting>
        </>
      )}
    </EditDialog>
  );
}

/** Callers a model writes from what the agent is; each is the agent's only once kept. */
export function ProposePanel({ agent, taken, onKept, onClose }: { agent: string; taken: ReadonlySet<string>; onKept: (callers: Persona[]) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [about, setAbout] = useState("");
  const [proposed, setProposed] = useState<ProposedPersona[] | null>(null);
  const [asking, setAsking] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const ask = async (): Promise<void> => {
    setAsking(true);
    setRefused(null);
    try {
      setProposed((await proposeCallers(credentials, agent, about)).personas);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setAsking(false);
    }
  };

  const keep = async (one: ProposedPersona): Promise<void> => {
    setRefused(null);
    try {
      const { name, ...written } = one;
      onKept(await writeCaller(credentials, agent, name, written));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <SidePanel
      title="Generate callers"
      icon="personas"
      about={`A model reads ${agent}'s prompt, tools and knowledge and writes the people most likely to phone it. Nothing is saved until you keep one. Each time you ask spends one evaluation.`}
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            <button type="button" className="cfg-save" disabled={asking} onClick={() => void ask()}>
              {asking ? "Writing them…" : proposed === null ? "Write callers" : "Write others"}
            </button>
          </div>
        </>
      }
    >
      <Field label="Somebody in particular?">
        <textarea className="cfg-input cfg-area" aria-label="Somebody in particular?" rows={2} placeholder="Optional. People who want to cancel, parents booking for a child…" value={about} onChange={(event) => setAbout(event.target.value)} />
      </Field>
      {proposed?.length === 0 && <p className="dash-quiet">It wrote none. Say who you are after and ask again.</p>}
      {proposed?.map((one) => (
        <div key={one.name} className="tst-proposed">
          <span className="tst-proposed-top">
            <span className="tst-proposed-name">{one.name}</span>
            {taken.has(one.name) ? (
              <Badge quiet>Kept</Badge>
            ) : (
              <button type="button" className="app-button" onClick={() => void keep(one)}>
                Keep
              </button>
            )}
          </span>
          <p className="tst-words">{one.goal}</p>
          <p className="dash-quiet">{one.style}</p>
        </div>
      ))}
    </SidePanel>
  );
}
