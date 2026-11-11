/** Everything else an agent is set to, a row each: what it does, what runs now, whose word that is, and the pencil that changes it — none where the class set it. */

import { useState, type ReactNode } from "react";

import type { JudgingSettings } from "../judges/door";
import { knobOf, Origin, type From } from "./corner";
import type { LexiconBody, Report, TuningAnswer, TuningBody } from "./door";
import { HangupEditor, hangupSaid } from "./hangup-editor";
import { LanguageEditor, languageName } from "./language-editor";
import { LexiconEditor } from "./lexicon-editor";
import { splitWord } from "./stage-editor";
import { brandOf, JudgeEditor, Pencil, voiceOf } from "./stages";
import { ZoneEditor } from "./zone-editor";

export type Save = (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => Promise<boolean>;
type Editing = "language" | "timezone" | "judge" | "hangup" | "lexicon";

const IN_THE_CLASS = "Declared in the class";

/** What a row says runs now: the value, and a quieter line under it when the value alone would not explain itself. */
interface Said {
  main: string;
  note?: string | undefined;
  /** Nobody chose it: said in the quiet colour. */
  unset?: boolean;
}

function Row({ name, about, said, from, readOnly, onEdit }: { name: string; about: string; said: Said; from: From; readOnly: boolean; onEdit: () => void }): ReactNode {
  return (
    <div className="cfg-set">
      <div className="cfg-set-words">
        <span className="cfg-set-name">{name}</span>
        <span className="cfg-set-about">{about}</span>
      </div>
      <div className="cfg-set-said">
        <span className={said.unset === true ? "cfg-set-main cfg-set-unset dash-clip" : "cfg-set-main dash-clip"} title={said.main}>
          {said.main}
        </span>
        {said.note !== undefined && <span className="cfg-set-note dash-clip">{said.note}</span>}
      </div>
      <Origin from={from} />
      {from !== "class" && !readOnly ? <Pencil label={`Change ${name.toLowerCase()}`} onClick={onEdit} /> : <span />}
    </div>
  );
}

function plural(count: number, one: string): string {
  return `${count} ${one}${count === 1 ? "" : "s"}`;
}

/** A model named `vendor/model`, as a row says it: the model, and whose it is under it. */
function modelSaid(vendor: string, model: string): Said {
  return model === "" ? { main: `${brandOf(vendor)}'s default` } : { main: model, note: vendor === "" ? undefined : brandOf(vendor) };
}

function lexiconSaid(lexicon: LexiconBody): Said {
  if (lexicon.said.length === 0 && lexicon.heard.length === 0) return { main: "Empty", note: "The voice and the transcriber run as they come", unset: true };
  const [first, ...rest] = lexicon.said;
  const shown = first === undefined ? "No pronunciations" : `${first.word} → ${first.spoken}${rest.length === 0 ? "" : `, and ${rest.length} more`}`;
  return { main: shown, note: lexicon.heard.length === 0 ? "No words to hear" : `${plural(lexicon.heard.length, "word")} to hear` };
}

interface Props {
  readOnly: boolean;
  report: Report;
  answer: TuningAnswer;
  config: TuningBody;
  fixed: ReadonlySet<string>;
  /** The words in effect, whose they are, and which of `says` and `hears` the class declares; null while they are read. */
  lexicon: LexiconBody | null;
  lexiconFrom: From;
  lexiconFixed: ReadonlySet<string>;
  /** The organization's own judging, or null where this key cannot read it. */
  judging: JudgingSettings | null;
  saving: boolean;
  refused: string | null;
  onSave: Save;
  onSaveLexicon: (lexicon: LexiconBody) => Promise<boolean>;
  onOpened: () => void;
  onKept: () => Promise<void>;
}

export function SettingsList({ readOnly, report, answer, config, fixed, lexicon, lexiconFrom, lexiconFixed, judging, saving, refused, onSave, onSaveLexicon, onOpened, onKept }: Props): ReactNode {
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
  // What the class declares is the class's whatever a corner holds; the rest is the nearest corner's, knob by knob.
  const fromOf = (name: string, from: From): From => (fixed.has(name) ? "class" : from);
  const ears = brandOf(report.hears.vendor);
  const voice = brandOf(report.speaks.vendor);

  const language = knobOf(answer, "language");
  const tag = language.value ?? report.speaks.language ?? report.hears.language ?? null;
  const languageSaid: Said = tag === null ? { main: "Not set", note: `${ears} and ${voice} each run their own default`, unset: true } : { main: languageName(tag) ?? tag, note: `${tag}, told to ${ears} and ${voice}` };

  const zone = knobOf(answer, "timezone");
  const zoneSaid: Said = fixed.has("timezone") ? { main: IN_THE_CLASS } : zone.value === null ? { main: "Not set", note: "The agent is told the day, and no hour", unset: true } : { main: zone.value };

  const judge = knobOf(answer, "judge");
  const ofTheOrg = judging?.model ?? null;
  const judgeOff = judging?.on === false ? "Judging at hang-up is off for the organization" : undefined;
  const theirs = ofTheOrg === null ? "Pinecall's judge" : `The organization's: ${ofTheOrg.model}`;
  const named = judge.value === null ? null : splitWord(judge.value, report.providers);
  const judgeSaid: Said = fixed.has("judge") ? { main: IN_THE_CLASS } : named !== null ? modelSaid(named.vendor, named.model) : ofTheOrg !== null ? modelSaid(ofTheOrg.provider, ofTheOrg.model) : { main: "Pinecall's judge", unset: true };
  const judgeFrom = fromOf("judge", judge.value !== null ? judge.from : ofTheOrg !== null ? "organization" : "pinecall");

  const hangup = knobOf(answer, "hangup");
  const hangupRow: Said = fixed.has("hangup") ? { main: IN_THE_CLASS } : { main: hangupSaid(hangup.value), note: hangup.value === null ? "Only the caller ends the call" : "It says goodbye, then ends the call", unset: hangup.value === null };

  const picked = voiceOf(report);
  const speaks = picked === null ? null : { ...report.speaks, voice_id: picked };
  const wordsLocked = lexiconFixed.has("says") && lexiconFixed.has("hears");

  return (
    <section className="dash-card" aria-label="Everything else">
      <div className="dash-card-top">
        <span className="dash-eyebrow">Behaviour</span>
      </div>
      <div className="cfg-sets">
        <Row name="Language" about="What the transcriber expects and the voice speaks." said={languageSaid} from={fromOf("language", language.from)} readOnly={readOnly} onEdit={() => open("language")} />
        <Row name="Time zone" about="The clock every call opens on." said={zoneSaid} from={fromOf("timezone", zone.from)} readOnly={readOnly} onEdit={() => open("timezone")} />
        <Row name="Judge model" about="The model that grades this agent's calls." said={{ ...judgeSaid, note: judgeOff ?? judgeSaid.note }} from={judgeFrom} readOnly={readOnly} onEdit={() => open("judge")} />
        <Row name="Hang up" about="Whether the agent may end the call itself." said={hangupRow} from={fromOf("hangup", hangup.from)} readOnly={readOnly} onEdit={() => open("hangup")} />
        {lexicon !== null && <Row name="Lexicon" about="Words it must say right, and hear right." said={wordsLocked ? { main: IN_THE_CLASS } : lexiconSaid(lexicon)} from={wordsLocked ? "class" : lexiconFrom} readOnly={readOnly} onEdit={() => open("lexicon")} />}
      </div>
      {editing === "language" && <LanguageEditor initial={language.value ?? ""} ears={ears} voice={voice} saving={saving} refused={refused} onClose={close} onSave={(text) => (text === "" ? save({}, ["language"]) : save({ language: text }))} />}
      {editing === "timezone" && <ZoneEditor initial={zone.value ?? ""} saving={saving} refused={refused} onClose={close} onSave={(next) => (next === "" ? save({}, ["timezone"]) : save({ timezone: next }))} />}
      {editing === "judge" && <JudgeEditor report={report} config={{ ...config, judge: judge.value }} unset={theirs} saving={saving} refused={refused} onClose={close} onSave={(changed, drop) => void save(changed, drop)} onKept={onKept} />}
      {editing === "hangup" && <HangupEditor initial={hangup.value} saving={saving} refused={refused} onClose={close} onSave={(next) => (next === null ? save({}, ["hangup"]) : save({ hangup: next }))} />}
      {editing === "lexicon" && lexicon !== null && <LexiconEditor lexicon={lexicon} fixed={lexiconFixed} speaks={speaks} saving={saving} refused={refused} onClose={close} onSave={(next) => void onSaveLexicon(next).then((done) => done && close())} />}
    </section>
  );
}
