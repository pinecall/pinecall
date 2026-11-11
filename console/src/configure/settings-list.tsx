/** Everything else an agent is set to, a row each: what it is now and the pencil that changes it — none where the class set it. */

import { useState, type ReactNode } from "react";

import { Field } from "../ui/setting";
import { Select } from "../ui/select";
import { EditDialog } from "./dialog";
import { ZoneEditor } from "./zone-editor";
import type { LexiconBody, Report, TuningBody } from "./door";
import { JudgeEditor, Locked, Pencil } from "./stages";

export type Save = (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => Promise<boolean>;
type Editing = "language" | "timezone" | "judge" | "hangup" | "lexicon";

const lines = (text: string): string[] =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");

function Row({ readOnly, name, value, locked, onEdit }: { readOnly: boolean; name: string; value: string; locked: boolean; onEdit: () => void }): ReactNode {
  return (
    <div className="cfg-row">
      <span className="cfg-row-name">{name}</span>
      <span className="cfg-row-value dash-clip" title={locked ? undefined : value}>
        {locked ? <Locked /> : value}
      </span>
      {!locked && !readOnly && <Pencil label={`Change ${name.toLowerCase()}`} onClick={onEdit} />}
    </div>
  );
}

function plural(count: number, one: string): string {
  return `${count} ${one}${count === 1 ? "" : "s"}`;
}

interface Props {
  readOnly: boolean;
  report: Report;
  config: TuningBody;
  fixed: ReadonlySet<string>;
  lexicon: LexiconBody | null;
  lexiconFixed: ReadonlySet<string>;
  saving: boolean;
  refused: string | null;
  onSave: Save;
  onSaveLexicon: (lexicon: LexiconBody) => Promise<boolean>;
  onOpened: () => void;
  onKept: () => Promise<void>;
}

export function SettingsList(props: Props): ReactNode {
  const { readOnly, report, config, fixed, lexicon, lexiconFixed, saving, refused, onSave, onSaveLexicon, onOpened, onKept } = props;
  const [editing, setEditing] = useState<Editing | null>(null);
  const open = (what: Editing): void => {
    onOpened();
    setEditing(what);
  };
  const close = (): void => setEditing(null);
  const save: Save = async (changed, drop) => {
    const done = await onSave(changed, drop);
    if (done) close();
    return done;
  };

  const hangup = config.hangup == null ? "Never: the caller hangs up" : config.hangup.when == null || config.hangup.when === "" ? "When it judges the call is over" : `When ${config.hangup.when}`;
  const lexiconLocked = lexiconFixed.has("says") && lexiconFixed.has("hears");

  return (
    <section className="dash-card" aria-label="Everything else">
      <div className="dash-card-top">
        <span className="dash-eyebrow">Behaviour</span>
      </div>
      <div className="cfg-rows">
        <Row readOnly={readOnly} name="Language" value={config.language ?? report.speaks.language ?? "Each vendor's default"} locked={fixed.has("language")} onEdit={() => open("language")} />
        <Row readOnly={readOnly} name="Time zone" value={config.timezone ?? (fixed.has("timezone") ? "The class's own" : "None: the agent is told no hour")} locked={fixed.has("timezone")} onEdit={() => open("timezone")} />
        <Row readOnly={readOnly} name="Judge model" value={config.judge ?? "The organization's choice"} locked={fixed.has("judge")} onEdit={() => open("judge")} />
        <Row readOnly={readOnly} name="Hang up" value={hangup} locked={fixed.has("hangup")} onEdit={() => open("hangup")} />
        <Row readOnly={readOnly} name="Lexicon" value={lexicon === null ? "—" : `${plural(lexicon.said.length, "pronunciation")}, ${plural(lexicon.heard.length, "word")} to hear`} locked={lexiconLocked} onEdit={() => open("lexicon")} />
      </div>
      {editing === "language" && <TextEditor title="Language" label="A language tag: en, es, pt-BR" initial={config.language ?? ""} saving={saving} refused={refused} onClose={close} onSave={(text) => (text === "" ? save({}, ["language"]) : save({ language: text }))} />}
      {editing === "timezone" && <ZoneEditor initial={config.timezone ?? ""} saving={saving} refused={refused} onClose={close} onSave={(zone) => (zone === "" ? save({}, ["timezone"]) : save({ timezone: zone }))} />}
      {editing === "judge" && <JudgeEditor report={report} config={config} saving={saving} refused={refused} onClose={close} onSave={(changed, drop) => void save(changed, drop)} onKept={onKept} />}
      {editing === "hangup" && <HangupEditor config={config} saving={saving} refused={refused} onClose={close} onSave={save} />}
      {editing === "lexicon" && lexicon !== null && <LexiconEditor lexicon={lexicon} fixed={lexiconFixed} saving={saving} refused={refused} onClose={close} onSave={(next) => void onSaveLexicon(next).then((done) => done && close())} />}
    </section>
  );
}

interface Editor {
  saving: boolean;
  refused: string | null;
  onClose: () => void;
}

function TextEditor({ title, label, initial, saving, refused, onClose, onSave }: Editor & { title: string; label: string; initial: string; onSave: (text: string) => Promise<boolean> }): ReactNode {
  const [text, setText] = useState(initial);
  return (
    <EditDialog title={title} saving={saving} refused={refused} onClose={onClose} onSave={() => void onSave(text.trim())}>
      <label className="cfg-field">
        {label}
        <input className="cfg-input" value={text} autoFocus spellCheck={false} onChange={(event) => setText(event.target.value)} />
      </label>
    </EditDialog>
  );
}

function HangupEditor({ config, saving, refused, onClose, onSave }: Editor & { config: TuningBody; onSave: Save }): ReactNode {
  const when = config.hangup?.when ?? "";
  const [mode, setMode] = useState<"never" | "any" | "when">(config.hangup == null ? "never" : when === "" ? "any" : "when");
  const [text, setText] = useState(when);
  const save = (): void => {
    if (mode === "never") void onSave({}, ["hangup"]);
    else void onSave({ hangup: { when: mode === "when" ? text.trim() : "" } });
  };
  return (
    <EditDialog title="Hang up" saving={saving} refused={refused} onClose={onClose} onSave={save}>
      <Field label="May the agent end the call?">
        <Select
          items={[
            { value: "never", label: "Never: the caller hangs up" },
            { value: "any", label: "When it judges the call is over" },
            { value: "when", label: "Only when…" },
          ]}
          value={mode}
          label="May the agent end the call?"
          onChange={(picked) => setMode(picked as typeof mode)}
        />
      </Field>
      {mode === "when" && (
        <label className="cfg-field">
          When
          <input className="cfg-input" value={text} placeholder="the caller has their appointment" onChange={(event) => setText(event.target.value)} />
        </label>
      )}
    </EditDialog>
  );
}

function LexiconEditor({ lexicon, fixed, saving, refused, onClose, onSave }: Editor & { lexicon: LexiconBody; fixed: ReadonlySet<string>; onSave: (lexicon: LexiconBody) => void }): ReactNode {
  const [said, setSaid] = useState(lexicon.said.map((one) => `${one.word} = ${one.spoken}`).join("\n"));
  const [heard, setHeard] = useState(lexicon.heard.join("\n"));
  const [wrong, setWrong] = useState<string | null>(null);
  const save = (): void => {
    const pairs = lines(said).map((line) => line.split("=").map((part) => part.trim()));
    const bad = pairs.find((pair) => pair.length !== 2 || pair[0] === "" || pair[1] === "");
    if (bad !== undefined) return setWrong(`Write it as word = how it is said: "${bad.join("=")}"`);
    setWrong(null);
    onSave({ said: pairs.map(([word, spoken]) => ({ word: word ?? "", spoken: spoken ?? "" })), heard: lines(heard) });
  };
  return (
    <EditDialog title="Lexicon" saving={saving} refused={wrong ?? refused} onClose={onClose} onSave={save}>
      <label className="cfg-field">
        How the voice says a word, one per line: word = how it is said
        <textarea className="cfg-input cfg-area" rows={5} value={said} disabled={fixed.has("says")} placeholder="Nginx = engine x" onChange={(event) => setSaid(event.target.value)} />
      </label>
      <label className="cfg-field">
        Words the ears must know, one per line
        <textarea className="cfg-input cfg-area" rows={5} value={heard} disabled={fixed.has("hears")} onChange={(event) => setHeard(event.target.value)} />
      </label>
    </EditDialog>
  );
}
