/** Settings form, one section at a time: pipeline, conversation, memory, knowledge, bases. */

import { useState, type FormEvent, type ReactNode } from "react";

import { type TuningBody } from "@pinecall/core/wire/rest-org";
import { type KnowledgeBase } from "@pinecall/core/wire/rest-retrieval";

import type { Provider } from "../../lib/catalogue";
import { Button, Input, Tabs } from "../../ui";
import { BasesSection } from "./bases";
import { ConversationSection } from "./conversation";
import { LanguageField } from "./language";
import type { Stage } from "../pipeline/door";
import { EndOfTurnField, FixedByTheClass, PluginFields, TemperatureField } from "./plugin";
import { StageSection, VoiceField } from "./stages";
import { configOf, typedOf, type Change, type Modeled, type Plugin, type Typed } from "./typed";
import { KnowledgeSection, MemorySection } from "./words";

export type Section = "hears" | "decides" | "speaks" | "judged" | "conversation" | "memory" | "knowledge" | "bases";

const SECTIONS: readonly { tab: Section; name: string }[] = [
  { tab: "hears", name: "STT" },
  { tab: "decides", name: "LLM" },
  { tab: "speaks", name: "Voice" },
  { tab: "judged", name: "Judge" },
  { tab: "conversation", name: "Conversation" },
  { tab: "memory", name: "Memory" },
  { tab: "knowledge", name: "Knowledge" },
  { tab: "bases", name: "Bases" },
];

// A key with `words` but not `pipeline` edits only the opening, memory and knowledge.
const WORDS: readonly Section[] = ["conversation", "memory", "knowledge"];

/** Sections a key may edit, in display order. */
export function sectionsFor(wordsOnly: boolean): readonly { tab: Section; name: string }[] {
  return wordsOnly ? SECTIONS.filter((one) => WORDS.includes(one.tab)) : SECTIONS;
}

export function SettingsForm({
  standing,
  version,
  wordsOnly,
  language,
  providers,
  defaults,
  models,
  bases,
  fixed,
  running,
  section,
  onPickSection,
  saving,
  error,
  onSave,
}: {
  standing: TuningBody;
  /** Version the form was opened at; the save is checked against it. */
  version: number | null;
  wordsOnly: boolean;
  /** Agent's language for listing voices; null when undeclared. */
  language: string | null;
  providers: readonly Provider[];
  defaults: Readonly<Record<string, string>>;
  models: Readonly<Record<string, readonly string[]>>;
  /** Bases in this world for the Bases section; null while loading. */
  bases: readonly KnowledgeBase[] | null;
  /** The settings the agent's class declares itself, by the declaration's names: shown, never edited. */
  fixed: ReadonlySet<string>;
  /** What the next call runs at each stage, where the class's value is read from; null while asked for. */
  running: { hears: Stage; decides: Stage; speaks: Stage } | null;
  section: Section;
  onPickSection: (section: Section) => void;
  saving: boolean;
  error: string | null;
  onSave: (config: TuningBody, ifVersion: number | null, note: string | null) => Promise<void>;
}): ReactNode {
  const vendors = new Set(providers.map((one) => one.name));
  const [typed, setTyped] = useState<Typed>(() => typedOf(standing, vendors));
  const [saved, setSaved] = useState(false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const change: Change = (field, value) => {
    setSaved(false);
    setTyped({ ...typed, [field]: value });
  };
  const plug = (modality: Modeled) => (plugin: Plugin) => {
    setSaved(false);
    setInvalid(null);
    setTyped({ ...typed, plugins: { ...typed.plugins, [modality]: plugin } });
  };
  const knob = (field: "stt" | "llm" | "tts" | "judge") => (picked: Typed["stt"]) => {
    setSaved(false);
    // Voices are per vendor: changing the TTS vendor clears the voice.
    setTyped(field === "tts" && picked.vendor !== typed.tts.vendor ? { ...typed, tts: picked, voice: "" } : { ...typed, [field]: picked });
  };
  // Picked TTS vendor, else the runtime default (null until the pipeline report arrives).
  const speaking = typed.tts.vendor === "" ? (defaults["tts"] ?? null) : typed.tts.vendor;

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    let config;
    try {
      config = configOf(typed, wordsOnly, standing, fixed);
    } catch (refused) {
      setInvalid(refused instanceof Error ? refused.message : String(refused));
      return;
    }
    await onSave(config, version, typed.note.trim() === "" ? null : typed.note.trim());
    setSaved(true);
  };

  return (
    <form className="ui-card set-form" onSubmit={(event) => void save(event)}>
      <div className="set-tabs">
        <Tabs label="Settings" tabs={sectionsFor(wordsOnly)} on={section} onPick={onPickSection} />
      </div>
      {section === "hears" && (
        <StageSection modality="stt" title="Speech to text" blurb="What turns the caller's voice into words, and in which language." knob={typed.stt} providers={providers} defaults={defaults} models={models} onChange={knob("stt")} fixed={fixed.has("stt") ? { value: said(running?.hears) } : undefined}>
          {!fixed.has("stt") && <EndOfTurnField endOfTurn={typed.end_of_turn} onChange={(picked) => change("end_of_turn", picked)} />}
          {!fixed.has("stt") && <PluginFields modality="stt" vendor={vendorOf(typed.stt.vendor, defaults["stt"])} plugin={typed.plugins.stt} onChange={plug("stt")} />}
          {fixed.has("language") ? <FixedByTheClass label="Language" value={running?.hears.language} /> : <LanguageField language={typed.language} onChange={(language) => change("language", language)} />}
        </StageSection>
      )}
      {section === "decides" && (
        <StageSection modality="llm" title="Language model" blurb="The model that reads what the caller said and writes the answer." knob={typed.llm} providers={providers} defaults={defaults} models={models} onChange={knob("llm")} fixed={fixed.has("llm") ? { value: said(running?.decides) } : undefined}>
          {!fixed.has("llm") && (
            <>
              <TemperatureField temperature={typed.temperature} onChange={(temperature) => change("temperature", temperature)} />
              <PluginFields modality="llm" vendor={vendorOf(typed.llm.vendor, defaults["llm"])} plugin={typed.plugins.llm} onChange={plug("llm")} />
            </>
          )}
        </StageSection>
      )}
      {section === "speaks" && (
        <StageSection modality="tts" title="Voice" blurb="What says the answer out loud, and in which voice." knob={typed.tts} providers={providers} defaults={defaults} models={models} onChange={knob("tts")} fixed={fixed.has("voice") ? { value: said(running?.speaks, true) } : undefined}>
          {!fixed.has("voice") && (
            <>
              <VoiceField vendor={speaking} providers={providers} model={typed.tts.model === "" ? null : typed.tts.model} language={language} opening={typed.say} voice={typed.voice} onChange={(voice) => change("voice", voice)} />
              <PluginFields modality="tts" vendor={vendorOf(typed.tts.vendor, defaults["tts"])} plugin={typed.plugins.tts} onChange={plug("tts")} />
            </>
          )}
        </StageSection>
      )}
      {section === "judged" && (
        <StageSection
          modality="llm"
          title="Judge model"
          blurb="The model this agent's calls are judged on at hang-up. Unset, the org's choice in Quality ▸ Judges, else Pinecall's. On your org's own key — a model on your own server among them, through base_url — its evals are not billed."
          knob={typed.judge}
          providers={providers}
          defaults={defaults}
          models={models}
          onChange={knob("judge")}
          unset="The org's choice, else Pinecall's"
          fixed={fixed.has("judge") ? { value: null } : undefined}
        >
          {!fixed.has("judge") && typed.judge.vendor !== "" && <PluginFields modality="judge" vendor={typed.judge.vendor} plugin={typed.plugins.judge} onChange={plug("judge")} />}
        </StageSection>
      )}
      {section === "conversation" && <ConversationSection typed={typed} wordsOnly={wordsOnly} fixed={fixed} change={change} />}
      {section === "memory" && (fixed.has("memory") ? <ClassOnly title="Memory" label="What it remembers and never keeps" /> : <MemorySection typed={typed} change={change} />)}
      {section === "knowledge" && (fixed.has("knowledge") ? <ClassOnly title="Knowledge" label="What it knows by heart" /> : <KnowledgeSection typed={typed} change={change} />)}
      {section === "bases" && fixed.has("docs") && <ClassOnly title="Bases" label="The base it searches" />}
      {section === "bases" && !fixed.has("docs") && (
        <BasesSection
          rows={typed.bases}
          offered={bases}
          onChange={(rows) => {
            setSaved(false);
            setTyped({ ...typed, bases: rows });
          }}
        />
      )}
      <div className="set-save">
        <Input className="set-save-note" value={typed.note} placeholder="Why, for the history (optional)" aria-label="Why, for the history (optional)" onChange={(event) => change("note", event.target.value)} />
        <Button kind="primary" size="form" type="submit" disabled={saving}>
          {saving ? "Saving…" : version === null ? "Save as the first version" : `Save as v${version + 1}`}
        </Button>
        <span className={(invalid ?? error) !== null ? "set-save-said set-save-error" : "set-save-said"}>
          {invalid !== null ? invalid : error !== null ? error : saved ? "Kept. The next call runs on it." : "Every section is saved together, as one version. An empty field is the runtime's default."}
        </span>
      </div>
    </form>
  );
}

// What a stage runs, as one word: vendor/model, and the voice where there is one.
function said(stage: Stage | undefined, voiced = false): string | null {
  if (stage === undefined) return null;
  const word = stage.model === null ? stage.vendor : `${stage.vendor}/${stage.model}`;
  return voiced && stage.voice_id !== null ? `${word} · ${stage.voice_id}` : word;
}

function vendorOf(picked: string, runtimeDefault: string | undefined): string {
  return picked === "" ? (runtimeDefault ?? "the vendor") : picked;
}

/** A whole section the agent's class declares. */
function ClassOnly({ title, label }: { title: string; label: string }): ReactNode {
  return (
    <section className="set-section">
      <div className="set-section-head">
        <h2 className="set-section-title">{title}</h2>
      </div>
      <FixedByTheClass label={label} />
    </section>
  );
}
