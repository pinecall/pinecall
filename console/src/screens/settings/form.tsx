/** Settings form, one section at a time: pipeline, conversation, memory, knowledge, bases. */

import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { type TuningBody } from "@pinecall/core/wire/rest-org";
import { type KnowledgeBase } from "@pinecall/core/wire/rest-retrieval";

import type { Provider } from "../../lib/catalogue";
import { Icon, Input, Tabs } from "../../ui";
import { BasesSection } from "./bases";
import { ConversationSection } from "./conversation";
import { Pipeline, type Running, type Step } from "./pipeline";
import type { Stage } from "../pipeline/door";
import { FixedByTheClass } from "./plugin";
import { configOf, typedOf, type Change, type Modeled, type Plugin, type Typed } from "./typed";
import { KnowledgeSection, MemorySection } from "./words";

export type Section = "pipeline" | "conversation" | "memory" | "knowledge" | "bases";

const SECTIONS: readonly { tab: Section; name: string; icon: ReactNode }[] = [
  { tab: "pipeline", name: "Pipeline", icon: <Icon name="route" size={15} /> },
  { tab: "conversation", name: "Conversation", icon: <Icon name="chat" size={15} /> },
  { tab: "memory", name: "Memory", icon: <Icon name="memory" size={15} /> },
  { tab: "knowledge", name: "Knowledge", icon: <Icon name="book" size={15} /> },
  { tab: "bases", name: "Bases", icon: <Icon name="library" size={15} /> },
];

// A key with `words` but not `pipeline` edits only the opening, memory and knowledge.
const WORDS: readonly Section[] = ["conversation", "memory", "knowledge"];

/** Sections a key may edit, in display order. */
export function sectionsFor(wordsOnly: boolean): readonly { tab: Section; name: string; icon: ReactNode }[] {
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
  realtime,
  bases,
  fixed,
  running,
  own,
  section,
  onPickSection,
  step,
  onPickStep,
  bar,
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
  /** By vendor, the models that hear and speak themselves: one picked runs the voice calls alone. */
  realtime: Readonly<Record<string, readonly string[]>>;
  /** Bases in this world for the Bases section; null while loading. */
  bases: readonly KnowledgeBase[] | null;
  /** The settings the agent's class declares itself, by the declaration's names: shown, never edited. */
  fixed: ReadonlySet<string>;
  /** What the next call runs at each stage, where the class's value is read from; null while asked for. */
  running: { hears: Stage; decides: Stage; speaks: Stage; talks: Stage | null } | null;
  /** The vendors this org runs on its own key; every other is lent by the runtime. */
  own: ReadonlySet<string>;
  section: Section;
  onPickSection: (section: Section) => void;
  /** The stage open under the Pipeline's tiles. */
  step: Step;
  onPickStep: (step: Step) => void;
  /** Where the save bar is drawn: under the scrolling page, so it never covers a field. */
  bar: HTMLElement | null;
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
  const knob = (field: "stt" | "llm" | "tts" | "judge" | "realtime") => (picked: Typed["stt"]) => {
    setSaved(false);
    // Voices and a realtime model's options are per vendor: changing the vendor clears them.
    if (field === "tts" && picked.vendor !== typed.tts.vendor) setTyped({ ...typed, tts: picked, voice: "" });
    else if (field === "realtime" && picked.vendor !== typed.realtime.vendor) setTyped({ ...typed, realtime: picked, realtime_options: "" });
    else setTyped({ ...typed, [field]: picked });
  };
  const save = async (): Promise<void> => {
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

  const stages: Running | null =
    running === null
      ? null
      : { hears: said(running.hears), decides: said(running.decides), speaks: said(running.speaks, true), talks: said(running.talks ?? undefined), language: running.hears.language };

  return (
    <form className="set-form" onSubmit={(event) => event.preventDefault()}>
      <div className="set-tabs">
        <Tabs label="Settings" tabs={sectionsFor(wordsOnly)} on={section} onPick={onPickSection} />
      </div>
      {section === "pipeline" && (
        <Pipeline typed={typed} change={change} knob={knob} plug={plug} providers={providers} defaults={defaults} models={models} realtime={realtime} fixed={fixed} running={stages} language={language} own={own} step={step} onStep={onPickStep} />
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
      {bar !== null &&
        createPortal(
          <div className="set-save">
            <Input
              className="set-save-note"
              value={typed.note}
              placeholder="Why, for the history (optional)"
              aria-label="Why, for the history (optional)"
              onChange={(event) => change("note", event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void save();
              }}
            />
            <span className={(invalid ?? error) !== null ? "set-save-said set-save-error" : "set-save-said"}>
              {invalid !== null ? invalid : error !== null ? error : saved ? `Saved. The next call runs on ${version === null ? "it" : `v${version}`}.` : "Every section is saved together, as one version. An empty field is the runtime's default."}
            </span>
            <button type="button" className="set-save-button" disabled={saving} onClick={() => void save()}>
              <Icon name="save" size={15} />
              {saving ? "Saving…" : version === null ? "Save as the first version" : `Save as v${version + 1}`}
            </button>
          </div>,
          bar,
        )}
    </form>
  );
}

// What a stage runs, as one word: vendor/model, and the voice where there is one.
function said(stage: Stage | undefined, voiced = false): string | null {
  if (stage === undefined) return null;
  const word = stage.model === null ? stage.vendor : `${stage.vendor}/${stage.model}`;
  return voiced && stage.voice_id !== null ? `${word} · ${stage.voice_id}` : word;
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
