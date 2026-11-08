/** A Studio agent's greeting and system prompt: edited in the sandbox, each save a new release; read in production. An app's greeting: in its settings, unless its class sets it. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { WORLD } from "../lib/world";
import { readStudioAgent, saveStudioAgent, type StudioAgent } from "./door";
import { Locked } from "./stages";

type Definition = StudioAgent["definition"];
type Greeting = Definition["greeting"];
type Opening = "none" | "say" | "reply";

/** Keeps a change of the definition as a new release: which one, or null when it was refused. */
type Save = (change: Partial<Definition>) => Promise<number | null>;

const OPENINGS: readonly { value: Opening; name: string }[] = [
  { value: "none", name: "Caller speaks first" },
  { value: "say", name: "Say these words" },
  { value: "reply", name: "Let it greet" },
];

const HINTS: Readonly<Record<Opening, string>> = {
  none: "The agent picks up and listens.",
  say: "Said word for word the moment the call is answered.",
  reply: "An instruction, not a script: the agent opens in its own words.",
};

const LONGEST_GREETING = 1000;

const wordsIn = (text: string): number => (text.trim() === "" ? 0 : text.trim().split(/\s+/).length);

function openingOf(greeting: Greeting): Opening {
  if (greeting?.say != null) return "say";
  return greeting?.reply != null ? "reply" : "none";
}

function Saving({ editable, dirty, saving, disabled = false, said, onSave }: { editable: boolean; dirty: boolean; saving: boolean; disabled?: boolean; said: string | null; onSave: () => void }): ReactNode {
  return (
    <>
      {said !== null && !dirty && <span className="dash-quiet">{said}</span>}
      {editable && (
        <button type="button" className="cfg-save" disabled={!dirty || saving || disabled} onClick={onSave}>
          {saving ? "Saving…" : "Save"}
        </button>
      )}
    </>
  );
}

function GreetingForm({ kept, editable, locked = false, saving, onSave }: { kept: Greeting; editable: boolean; locked?: boolean; saving: boolean; onSave: (greeting: Greeting) => Promise<string | null> }): ReactNode {
  const [opening, setOpening] = useState<Opening>(openingOf(kept));
  const [text, setText] = useState(kept?.say ?? kept?.reply ?? "");
  const [said, setSaid] = useState<string | null>(null);
  const dirty = opening !== openingOf(kept) || (opening !== "none" && text !== (kept?.say ?? kept?.reply ?? ""));

  const save = async (): Promise<void> => {
    setSaid(null);
    const greeting = opening === "none" ? null : opening === "say" ? { say: text.trim() } : { reply: text.trim() };
    setSaid(await onSave(greeting));
  };

  return (
    <section className="dash-card" aria-label="Greeting">
      <div className="dash-card-top">
        <h3 className="cfg-title">Greeting</h3>
        <span className="cfg-prompt-end">
          {locked && <Locked />}
          <Saving editable={editable} dirty={dirty} saving={saving} disabled={opening !== "none" && text.trim() === ""} said={said} onSave={() => void save()} />
        </span>
      </div>
      <div className="dash-switch cfg-openings" role="radiogroup" aria-label="How the call opens">
        {OPENINGS.map((one) => (
          <button key={one.value} type="button" role="radio" aria-checked={opening === one.value} className={opening === one.value ? "dash-switch-on" : ""} disabled={!editable} onClick={() => setOpening(one.value)}>
            {one.name}
          </button>
        ))}
      </div>
      {opening !== "none" && (
        <textarea
          className="cfg-input cfg-area cfg-greeting"
          rows={3}
          maxLength={LONGEST_GREETING}
          aria-label={opening === "say" ? "The words said" : "The instruction the agent opens with"}
          placeholder={opening === "say" ? "Hello, thanks for calling. How can I help?" : "Greet the caller by name if you know it, and ask how you can help."}
          value={text}
          readOnly={!editable}
          onChange={(event) => setText(event.target.value)}
        />
      )}
      <p className="dash-quiet cfg-talks">{HINTS[opening]}</p>
    </section>
  );
}

function GreetingCard({ read, saving, onSave }: { read: StudioAgent; saving: boolean; onSave: Save }): ReactNode {
  const send = async (greeting: Greeting): Promise<string | null> => {
    const release = await onSave({ greeting });
    return release === null ? null : `Saved as release ${release}`;
  };
  return <GreetingForm kept={read.definition.greeting} editable={WORLD === "sandbox"} saving={saving} onSave={send} />;
}

export function AppGreeting({ kept, locked, readOnly, saving, refused, onSave }: { kept: Greeting; locked: boolean; readOnly: boolean; saving: boolean; refused: string | null; onSave: (greeting: Greeting) => Promise<boolean> }): ReactNode {
  const [failed, setFailed] = useState(false);
  const send = async (greeting: Greeting): Promise<string | null> => {
    const landed = await onSave(greeting);
    setFailed(!landed);
    return landed ? "Saved" : null;
  };
  return (
    <>
      {failed && refused !== null && <p className="cfg-refused">{refused}</p>}
      <GreetingForm kept={kept} editable={!locked && !readOnly} locked={locked} saving={saving} onSave={send} />
    </>
  );
}

function PromptCard({ read, saving, onSave }: { read: StudioAgent; saving: boolean; onSave: Save }): ReactNode {
  const [text, setText] = useState(read.definition.instructions);
  const [said, setSaid] = useState<string | null>(null);
  const editable = WORLD === "sandbox";
  const dirty = text !== read.definition.instructions;

  const save = async (): Promise<void> => {
    setSaid(null);
    const release = await onSave({ instructions: text });
    if (release !== null) setSaid(`Saved as release ${release}`);
  };

  return (
    <section className="dash-card" aria-label="System prompt">
      <div className="dash-card-top">
        <h3 className="cfg-title">System prompt</h3>
        <span className="cfg-prompt-end">
          <span className="dash-quiet">{wordsIn(text)} words</span>
          <Saving editable={editable} dirty={dirty} saving={saving} disabled={text.trim() === ""} said={said} onSave={() => void save()} />
        </span>
      </div>
      <textarea className="cfg-prompt" aria-label="System prompt" value={text} readOnly={!editable} spellCheck={false} onChange={(event) => setText(event.target.value)} />
    </section>
  );
}

export function StudioBrief({ agent, onSaved }: { agent: string; onSaved: () => void }): ReactNode {
  const credentials = useCredentials();
  const [read, setRead] = useState<StudioAgent | null>(null);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readStudioAgent(credentials, agent).then((agentRead) => !gone && setRead(agentRead), (failed: unknown) => !gone && setRefused(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  // Each card sends only its own part: what the other has typed and not saved stays in its box.
  const save: Save = async (change) => {
    if (read === null) return null;
    setSaving(true);
    setRefused(null);
    try {
      const saved = await saveStudioAgent(credentials, agent, { ...read.definition, ...change }, read.release);
      setRead(saved);
      onSaved();
      return saved.release;
    } catch (failed) {
      setRefused(saidBy(failed));
      return null;
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      {read === null && refused === null && <p className="dash-quiet">Reading the prompt…</p>}
      {read !== null && <GreetingCard read={read} saving={saving} onSave={save} />}
      {read !== null && <PromptCard read={read} saving={saving} onSave={save} />}
    </>
  );
}
