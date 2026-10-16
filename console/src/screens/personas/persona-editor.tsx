/** Persona editor form. */

import { useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Input, Select, SelectItem, TextArea } from "../../ui";
import type { Ambience, CallerBehavior } from "@pinecall/core/wire/rest-evals";
import { writePersona, type Persona, type Written } from "./door";
import { PlayedBy } from "./played-by";

// Same rule as `pinecall simulate --persona` and the gateway.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Text fields; empty means unset (the runtime's default). */
type Worded = "about" | "goal" | "style";

/** How a caller acts on a spoken line when nobody said otherwise. */
const STILL: CallerBehavior = { interrupts: 0, pause_s: 0, interferer_db: null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "television" };

// The dB under the caller a background plays at when it is first picked.
const A_BACKGROUND_DB = 15;

// Listener's noises into the agent's answers: never, or about this share of them.
const MURMURS = [
  { value: 0, label: "Never: listens in silence" },
  { value: 0.3, label: "Sometimes: an \"mm-hmm\" into a third of the answers" },
  { value: 0.7, label: "Often: into most answers" },
] as const;

// The caller's tempo against the voice as its vendor reads it.
const SPEEDS = [
  { value: 0.75, label: "Slow: three quarters of the voice's tempo" },
  { value: 0.9, label: "A little slower" },
  { value: 1, label: "As the voice reads it" },
  { value: 1.15, label: "A little faster" },
  { value: 1.3, label: "Fast: in a hurry" },
] as const;

// What plays behind the caller; "" is a quiet room, which is no level at all.
const BACKGROUNDS = [
  { value: "", label: "A quiet room" },
  { value: "television", label: "A television" },
  { value: "cafe", label: "A café: chatter over a room" },
  { value: "office", label: "An office: a hum" },
  { value: "street", label: "A street: traffic" },
] as const;

// How loud the background is, as dB under the caller's voice.
const LEVELS = [
  { value: 25, label: "Faint: 25 dB under them" },
  { value: 15, label: "Clearly there: 15 dB under" },
  { value: 8, label: "Loud: 8 dB under, hard to hear them" },
] as const;

// The share of the caller's packets the line loses.
const LOSSES = [
  { value: 0, label: "A good line" },
  { value: 0.02, label: "A few packets lost: 2%" },
  { value: 0.1, label: "A bad line: 10% lost" },
] as const;

// The share of the agent's answers the caller talks over, in words; the CLI's --interrupts takes any.
const TALKS_OVER = [
  { value: 0, label: "Never: waits for every answer" },
  { value: 0.2, label: "Now and then: about one answer in five" },
  { value: 0.5, label: "Often: about half the answers" },
  { value: 0.8, label: "Almost always" },
] as const;

// Seconds of silence before each of the caller's lines; the CLI's --pause takes any up to 10.
const PAUSES = [
  { value: 0, label: "No: answers at once" },
  { value: 1.5, label: "A little: 1.5 s before each line" },
  { value: 3, label: "Slow: 3 s, as someone thinking" },
  { value: 6, label: "Very slow: 6 s, looking for a paper" },
] as const;

export function PersonaEditor({
  owners,
  was,
  onSaved,
  onCancel,
}: {
  /** Whom the caller may be written for: one agent, or — every agent in view, a new caller — the org's. */
  owners: readonly string[];
  /** The persona being changed; undefined for a new one. */
  was: Persona | undefined;
  onSaved: (personas: Persona[], written: Pick<Persona, "agent" | "name">) => void;
  onCancel: () => void;
}): ReactNode {
  const credentials = useCredentials();
  const [agent, setAgent] = useState(was?.agent ?? owners[0] ?? "");
  // The name goes in the path, the rest in the body.
  const [name, setName] = useState(was?.name ?? "");
  const [written, setWritten] = useState<Written>(() =>
    was === undefined
      ? { about: "", goal: "", style: "", facts: {}, llm: "", tts: "", voice: "", expects: [], tags: [], behavior: STILL }
      : {
          about: was.about,
          goal: was.goal,
          style: was.style,
          facts: was.facts,
          llm: was.llm ?? "",
          tts: was.tts ?? "",
          voice: was.voice ?? "",
          expects: was.expects,
          tags: was.tags,
          behavior: was.behavior,
        },
  );
  // A new persona starts with one empty fact row.
  const [facts, setFacts] = useState<[string, string][]>(() => {
    const rows = Object.entries(written.facts ?? {});
    return rows.length > 0 ? rows : [["", ""]];
  });
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const set = (field: Worded, value: string): void => setWritten({ ...written, [field]: value });
  // What the gateway sent has every field; a caller being written starts still, so nothing here is missing.
  const acts = { ...STILL, ...(written.behavior ?? {}) } as CallerBehavior;
  const behave = (change: Partial<CallerBehavior>): void => setWritten({ ...written, behavior: { ...acts, ...change } });
  // Picking a background puts it at a level when there was none; a quiet room is no level at all.
  const background = (picked: string): void =>
    behave(picked === "" ? { interferer_db: null } : { ambience: picked as Ambience, interferer_db: acts.interferer_db ?? A_BACKGROUND_DB });
  const expects = (written.expects ?? []).join("\n");
  const setFact = (at: number, row: [string, string]): void => setFacts(facts.map((one, index) => (index === at ? row : one)));
  const nameOk = A_NAME.test(name);
  const ready = agent !== "" && nameOk && written.goal.trim() !== "" && written.style.trim() !== "";

  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      const kept = Object.fromEntries(facts.filter(([what]) => what.trim() !== "").map(([what, said]) => [what.trim(), said.trim()]));
      // Preserve `state` even though the form cannot edit it.
      const lines = (written.expects ?? []).map((line) => line.trim()).filter((line) => line !== "");
      const body: Written = { ...written, expects: lines, facts: kept, state: was?.state ?? {}, ...(was === undefined || was.name === name ? {} : { was: was.name }) };
      onSaved(await writePersona(credentials, agent, name, body), { agent, name });
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="psn-doc psn-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) void save();
      }}
    >
      <header className="psn-doc-head">
        <div>
          <h1 className="psn-doc-name">{was === undefined ? "New persona" : `Editing ${was.name}`}</h1>
          <p className="psn-doc-about">
            Kept by the gateway for {agent === "" ? "the agent you pick" : agent}: for this console and for <code>pinecall simulate --persona {name || "<name>"}</code>.
          </p>
        </div>
      </header>

      {owners.length > 1 && (
        <Row title="Agent" hint="The agent this caller rings: a persona is written to test one agent, and only that agent's simulations play it.">
          <Select aria-label="Agent" value={agent} onValueChange={(value) => setAgent(value)}>
            {owners.map((one) => (
              <SelectItem key={one} value={one}>
                {one}
              </SelectItem>
            ))}
          </Select>
        </Row>
      )}
      <Row title="Name" hint="What pinecall simulate --persona takes, and how the list names them. Lower-case words joined by hyphens.">
        <Input value={name} spellCheck={false} aria-label="Name" placeholder="price-shopper" onChange={(event) => setName(event.target.value.toLowerCase().replace(/\s+/g, "-"))} />
        {name !== "" && !nameOk && <p className="psn-bad">Only a–z, 0–9 and single hyphens between words.</p>}
      </Row>
      <Row title="Who they are" hint="One line for people reading the list. The model is not told it.">
        <Input value={written.about ?? ""} aria-label="Who they are" placeholder="A landlord who only wants a number" onChange={(event) => set("about", event.target.value)} />
      </Row>
      <Row title="What they want" hint="The goal the model pursues on every turn. Say it the way the caller would: specific, with the deadline if there is one.">
        <TextArea rows={3} value={written.goal} aria-label="What they want" placeholder="get a price for a deep clean of a three bedroom house before Friday" onChange={(event) => set("goal", event.target.value)} />
      </Row>
      <Row title="How they talk" hint="The manner, not the content: hurried, polite, suspicious, switches into Spanish, answers only what is asked.">
        <TextArea rows={2} value={written.style} aria-label="How they talk" placeholder="blunt, impatient, keeps asking for the price" onChange={(event) => set("style", event.target.value)} />
      </Row>
      <Row
        title="What they expect of the agent"
        hint="One line each, starting “The agent should…”: something the agent's prompt or knowledge says it can do. The expected-outcome judge holds every call of theirs to these at hang-up — the model playing them is never told. Nothing about how the call ends."
      >
        <TextArea
          rows={3}
          value={expects}
          aria-label="What they expect of the agent"
          placeholder={"The agent should give the price of a deep clean.\nThe agent should offer a day this week."}
          onChange={(event) => setWritten({ ...written, expects: event.target.value.split("\n") })}
        />
      </Row>
      <Row title="What they know about themselves" hint="The only facts they may state — asked for anything else, they say they do not know. One per row: what it is, and what they say.">
        <div className="psn-fact-rows">
          {facts.map(([what, said], at) => (
            <div className="psn-fact-row" key={at}>
              <Input size="sm" value={what} placeholder="their phone" aria-label="what it is" onChange={(event) => setFact(at, [event.target.value, said])} />
              <Input size="sm" value={said} placeholder="305 555 0101" aria-label="what they say" onChange={(event) => setFact(at, [what, event.target.value])} />
              <button type="button" className="psn-x" aria-label="remove this fact" onClick={() => setFacts(facts.filter((_, index) => index !== at))}>
                ×
              </button>
            </div>
          ))}
          <button type="button" className="psn-add" onClick={() => setFacts([...facts, ["", ""]])}>
            + Add a fact
          </button>
        </div>
      </Row>
      <Row
        title="Their voice"
        hint="The model that improvises them, and the vendor and voice their lines are read in, from what this box runs — listen before you pick. Unpicked is the runtime's choice: the callers' model, a voice the agent does not have."
      >
        <PlayedBy
          played={{ llm: written.llm ?? "", tts: written.tts ?? "", voice: written.voice ?? "" }}
          onChange={(played) => setWritten({ ...written, ...played })}
        />
        <div className="psn-acts psn-acts-one">
          <label className="psn-act">
            <span className="psn-act-name">How fast they speak</span>
            <Select value={String(acts.speed)} onValueChange={(value) => behave({ speed: Number(value) })} aria-label="How fast they speak">
              {SPEEDS.map((one) => (
                <SelectItem key={one.value} value={String(one.value)}>
                  {one.label}
                </SelectItem>
              ))}
              {!SPEEDS.some((one) => one.value === acts.speed) && <SelectItem value={String(acts.speed)}>{`${acts.speed}× the voice's tempo`}</SelectItem>}
            </Select>
          </label>
        </div>
      </Row>
      <Row
        title="How they act on a spoken line"
        hint="Heard only on a spoken simulation; a written one ignores these. Interrupting tests the agent's barge-in for real: the caller starts its next line while the agent is still talking. Murmuring tests that an mm-hmm does not stop it."
      >
        <div className="psn-acts">
          <label className="psn-act">
            <span className="psn-act-name">Interrupts the agent</span>
            <Select value={String(acts.interrupts)} onValueChange={(value) => behave({ interrupts: Number(value) })} aria-label="Interrupts the agent">
              {TALKS_OVER.map((one) => (
                <SelectItem key={one.value} value={String(one.value)}>
                  {one.label}
                </SelectItem>
              ))}
              {!TALKS_OVER.some((one) => one.value === acts.interrupts) && <SelectItem value={String(acts.interrupts)}>{`${Math.round(acts.interrupts * 100)}% of the answers`}</SelectItem>}
            </Select>
          </label>
          <label className="psn-act">
            <span className="psn-act-name">Murmurs while the agent talks</span>
            <Select value={String(acts.backchannels)} onValueChange={(value) => behave({ backchannels: Number(value) })} aria-label="Murmurs while the agent talks">
              {MURMURS.map((one) => (
                <SelectItem key={one.value} value={String(one.value)}>
                  {one.label}
                </SelectItem>
              ))}
              {!MURMURS.some((one) => one.value === acts.backchannels) && <SelectItem value={String(acts.backchannels)}>{`into ${Math.round(acts.backchannels * 100)}% of the answers`}</SelectItem>}
            </Select>
          </label>
          <label className="psn-act">
            <span className="psn-act-name">Takes time before speaking</span>
            <Select value={String(acts.pause_s)} onValueChange={(value) => behave({ pause_s: Number(value) })} aria-label="Takes time before speaking">
              {PAUSES.map((one) => (
                <SelectItem key={one.value} value={String(one.value)}>
                  {one.label}
                </SelectItem>
              ))}
              {!PAUSES.some((one) => one.value === acts.pause_s) && <SelectItem value={String(acts.pause_s)}>{`${acts.pause_s} s before each line`}</SelectItem>}
            </Select>
          </label>
          <label className="psn-act">
            <span className="psn-act-name">Where they call from</span>
            <Select value={acts.interferer_db === null ? "" : acts.ambience} onValueChange={background} aria-label="Where they call from">
              {BACKGROUNDS.map((one) => (
                <SelectItem key={one.value} value={one.value}>
                  {one.label}
                </SelectItem>
              ))}
            </Select>
          </label>
          {acts.interferer_db !== null && (
            <label className="psn-act">
              <span className="psn-act-name">How loud it is</span>
              <Select value={String(acts.interferer_db)} onValueChange={(value) => behave({ interferer_db: Number(value) })} aria-label="How loud the background is">
                {LEVELS.map((one) => (
                  <SelectItem key={one.value} value={String(one.value)}>
                    {one.label}
                  </SelectItem>
                ))}
                {!LEVELS.some((one) => one.value === acts.interferer_db) && <SelectItem value={String(acts.interferer_db)}>{`${acts.interferer_db} dB under them`}</SelectItem>}
              </Select>
            </label>
          )}
          <label className="psn-act">
            <span className="psn-act-name">The phone line</span>
            <Select value={String(acts.packet_loss)} onValueChange={(value) => behave({ packet_loss: Number(value) })} aria-label="The phone line">
              {LOSSES.map((one) => (
                <SelectItem key={one.value} value={String(one.value)}>
                  {one.label}
                </SelectItem>
              ))}
              {!LOSSES.some((one) => one.value === acts.packet_loss) && <SelectItem value={String(acts.packet_loss)}>{`${Math.round(acts.packet_loss * 100)}% of packets lost`}</SelectItem>}
            </Select>
          </label>
        </div>
      </Row>

      <footer className="psn-form-foot">
        <Button type="submit" kind="primary" disabled={!ready || saving}>
          {saving ? "Saving…" : was === undefined ? "Create persona" : "Save"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        {!ready && <span className="psn-form-need">A name, what they want and how they talk are needed.</span>}
      </footer>
      {refused !== null && <p className="psn-refused">{refused}</p>}
    </form>
  );
}

function Row({ title, hint, children }: { title: string; hint: string; children: ReactNode }): ReactNode {
  return (
    <div className="psn-field">
      <div className="psn-field-words">
        <span className="psn-sec-title">{title}</span>
        <span className="psn-sec-hint">{hint}</span>
      </div>
      <div className="psn-field-input">{children}</div>
    </div>
  );
}
