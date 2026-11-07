/** Voice & models for ONE test room, as a panel or a tab: the voice and the models a room is tried with, over the agent's own — asked at the room's token and kept nowhere. */

import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { brandOf } from "../../lib/catalogue";
import { asking, type TestValues } from "../../lib/test-values";
import { Button, Icon, Label, Select, SelectItem, type IconName } from "../../ui";
import { readPipeline, type Report } from "../pipeline/door";
import { readVendors } from "../providers";
import { languageSaid, languagesWith } from "./language";
import { StageSection, VoiceField } from "./stages";
import { unpickedVoice } from "./voice-picker";
import { knobOf, wordOf, type Knob, type Modality } from "./typed";

/** What the panel edits: each stage as a vendor and a model, the voice and the language; empty is the agent's own. */
interface Draft {
  stt: Knob;
  llm: Knob;
  tts: Knob;
  voice: string;
  language: string;
}

/** The panel over the side of a room: the Playground's. */
export function TestValuesPanel({ agent, values, onApply, onClose }: { agent: string; values: TestValues | null; onApply: (values: TestValues | null) => void; onClose: () => void }): ReactNode {
  const { report, own, refused } = useStages(agent);
  return (
    <aside className="set-test" aria-label="Voice and models for this test room">
      <header className="set-test-head">
        <span className="set-test-words">
          <span className="set-test-title">Voice &amp; models</span>
          <span className="set-test-under">Try another voice or model in this chat. {agent}&apos;s saved settings don&apos;t change.</span>
        </span>
        <button type="button" className="set-test-close" aria-label="Close" onClick={onClose}>
          <Icon name="cross" size={15} />
        </button>
      </header>
      {report === null ? <p className="set-help set-test-quiet">{refused ?? "Asking the gateway…"}</p> : <Form report={report} own={own} values={values} onApply={onApply} onClose={onClose} />}
    </aside>
  );
}

/** The same form as a tab of its own: Studio's, beside the definition. */
export function TestValuesTab({ agent, values, onApply }: { agent: string; values: TestValues | null; onApply: (values: TestValues | null) => void }): ReactNode {
  const { report, own, refused } = useStages(agent);
  return (
    <div className="set-test-tab">
      {report === null ? <p className="set-help set-test-quiet">{refused ?? "Asking the gateway…"}</p> : <Form report={report} own={own} values={values} onApply={onApply} onClose={() => undefined} />}
    </div>
  );
}

// What the form lists: the agent's stages as they run, the vendors and their models, and which vendors run on the org's own key.
function useStages(agent: string): { report: Report | null; own: ReadonlySet<string>; refused: string | null } {
  const credentials = useCredentials();
  const [report, setReport] = useState<Report | null>(null);
  const [own, setOwn] = useState<ReadonlySet<string>>(new Set());
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readPipeline(credentials, agent).then(
      (read) => !gone && setReport(read),
      (failed: unknown) => !gone && setRefused(failed instanceof Error ? failed.message : String(failed)),
    );
    readVendors(credentials).then(
      (read) => !gone && setOwn(new Set(read)),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);
  return { report, own, refused };
}

function draftOf(values: TestValues | null, vendors: ReadonlySet<string>): Draft {
  return {
    stt: knobOf(values?.stt, vendors),
    llm: knobOf(values?.llm, vendors),
    tts: knobOf(values?.tts, vendors),
    voice: values?.voice ?? "",
    language: values?.language ?? "",
  };
}

// What the room asks for: only what differs from the agent's own, as the token takes it.
function valuesOf(draft: Draft): TestValues | null {
  const asked: TestValues = {
    ...(wordOf(draft.stt) === "" ? {} : { stt: wordOf(draft.stt) }),
    ...(wordOf(draft.llm) === "" ? {} : { llm: wordOf(draft.llm) }),
    ...(wordOf(draft.tts) === "" ? {} : { tts: wordOf(draft.tts) }),
    ...(draft.voice === "" ? {} : { voice: draft.voice }),
    ...(draft.language === "" ? {} : { language: draft.language }),
  };
  return asking(asked) ? asked : null;
}

const STEPS: readonly { step: Modality; icon: IconName; name: string; stage: "hears" | "decides" | "speaks" }[] = [
  { step: "stt", icon: "ear", name: "Hears", stage: "hears" },
  { step: "llm", icon: "memory", name: "Thinks", stage: "decides" },
  { step: "tts", icon: "speaker", name: "Speaks", stage: "speaks" },
];

function Form({ report, own, values, onApply, onClose }: { report: Report; own: ReadonlySet<string>; values: TestValues | null; onApply: (values: TestValues | null) => void; onClose: () => void }): ReactNode {
  const [draft, setDraft] = useState(() => draftOf(values, new Set(report.providers.map((one) => one.name))));
  // The tab is for the voice first: it opens on Speaks.
  const [step, setStep] = useState<Modality>("tts");
  const set = (part: Partial<Draft>): void => setDraft((was) => ({ ...was, ...part }));
  const speaking = draft.tts.vendor === "" ? report.speaks.vendor : draft.tts.vendor;
  const model = draft.tts.model === "" ? (draft.tts.vendor === "" ? report.speaks.model : null) : draft.tts.model;
  const language = draft.language === "" ? report.speaks.language : draft.language;
  const unpicked = unpickedVoice(report.voice_defaults, speaking, language);
  const apply = (next: TestValues | null): void => {
    if (next === null) setDraft(draftOf(null, new Set()));
    onApply(next);
    onClose();
  };

  // What a tile says the stage runs: the agent's own, or what this chat tries instead.
  const runsAt = (at: Modality): { value: string; under: string } => {
    const running = report[STEPS.find((one) => one.step === at)!.stage];
    const picked = draft[at];
    const vendor = picked.vendor === "" ? running.vendor : picked.vendor;
    const chosen = picked.model !== "" ? picked.model : picked.vendor === "" ? running.model : (report.runs[`${at}/${vendor}`] ?? null);
    const value = chosen === null ? vendor : `${vendor}/${chosen}`;
    const under =
      at === "stt"
        ? language === null
          ? "language not set"
          : `language ${language}`
        : at === "tts"
          ? draft.voice !== ""
            ? `as ${draft.voice}`
            : unpicked === null
              ? "the model's own voice"
              : `as ${unpicked}`
          : wordOf(picked) === ""
            ? "same as the agent"
            : "for this chat";
    return { value, under };
  };

  // A knob of a stage: the agent's own vendor runs when none is picked, so a model picked alone is that vendor's.
  const stage = (at: Modality): { knob: Knob; runs: Readonly<Record<string, string>>; onChange: (knob: Knob) => void } => {
    const running = report[STEPS.find((one) => one.step === at)!.stage];
    const theirs = running.model ?? report.runs[`${at}/${running.vendor}`];
    return {
      knob: draft[at],
      runs: theirs === undefined ? report.runs : { ...report.runs, [`${at}/${running.vendor}`]: theirs },
      onChange: (knob) => {
        const picked = knob.vendor === "" && knob.model !== "" ? { vendor: running.vendor, model: knob.model } : knob;
        set(at === "tts" ? { tts: picked, voice: "" } : at === "stt" ? { stt: picked } : { llm: picked });
      },
    };
  };
  const shared = { providers: report.providers, defaults: report.defaults, models: report.models, own };

  return (
    <div className="set-test-body">
      <div className="set-tiles" role="tablist" aria-label="Stages of a turn">
        {STEPS.map((tile) => {
          const at = runsAt(tile.step);
          return (
            <button key={tile.step} type="button" role="tab" aria-selected={step === tile.step} className={step === tile.step ? "set-tile set-tile-on" : "set-tile"} onClick={() => setStep(tile.step)}>
              <span className="set-tile-name">
                <Icon name={tile.icon} size={15} />
                {tile.name}
              </span>
              <span className="set-tile-value">{at.value}</span>
              <span className="set-tile-under">{at.under}</span>
            </button>
          );
        })}
      </div>

      {step === "stt" && (
        <StageSection modality="stt" title="Hears" blurb="What turns the caller's voice into words, and in which language." {...shared} {...stage("stt")} unset={`Same as the agent · ${brandOf(report.hears.vendor)}`} unsetRuns={report.hears.vendor}>
          <div className="set-row">
            <div className="set-field">
              <Label>Language</Label>
              <Select value={draft.language} aria-label="Language" onValueChange={(picked) => set({ language: picked })}>
                <SelectItem value="">{report.speaks.language === null ? "Same as the agent · not set" : `Same as the agent · ${languageSaid(report.speaks.language)}`}</SelectItem>
                {languagesWith(draft.language)
                  .filter((tag) => tag !== report.speaks.language)
                  .map((tag) => (
                    <SelectItem key={tag} value={tag}>
                      {languageSaid(tag)}
                    </SelectItem>
                  ))}
              </Select>
            </div>
          </div>
        </StageSection>
      )}
      {step === "llm" && <StageSection modality="llm" title="Thinks" blurb="The model that reads what the caller said and writes the answer." {...shared} {...stage("llm")} unset={`Same as the agent · ${brandOf(report.decides.vendor)}`} unsetRuns={report.decides.vendor} />}
      {step === "tts" && (
        <StageSection modality="tts" title="Voice" blurb="Says the answer out loud." {...shared} {...stage("tts")} unset={`Same as the agent · ${brandOf(report.speaks.vendor)}`} unsetRuns={report.speaks.vendor}>
          <VoiceField
            vendor={speaking}
            providers={report.providers}
            model={model}
            language={language}
            opening={report.greeting?.say ?? ""}
            voice={draft.voice === "" ? (report.speaks.voice_id ?? "") : draft.voice}
            unpicked={unpicked}
            onChange={(voice) => set({ voice })}
          />
        </StageSection>
      )}

      <footer className="set-test-foot">
        <span className="set-help">Only this test chat changes; your agent&apos;s saved settings don&apos;t.</span>
        <Button size="md" onClick={() => apply(null)} disabled={values === null && valuesOf(draft) === null}>
          Reset
        </Button>
        <Button size="md" kind="primary" onClick={() => apply(valuesOf(draft))}>
          Apply
        </Button>
      </footer>
    </div>
  );
}
