/** Voice & models for ONE test room, as a panel or a tab: the voice and the models a room is tried with, over the agent's own — asked at the room's token and kept nowhere. */

import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { brandOf, doing, type Provider } from "../../lib/catalogue";
import { asking, type TestValues } from "../../lib/test-values";
import { Button, Icon, Select, SelectItem, type IconName } from "../../ui";
import { readPipeline, type Report, type Stage } from "../pipeline/door";
import { readVendors } from "../providers";
import { languageSaid, languagesWith } from "./language";
import { VoiceField } from "./stages";
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

function Form({ report, own, values, onApply, onClose }: { report: Report; own: ReadonlySet<string>; values: TestValues | null; onApply: (values: TestValues | null) => void; onClose: () => void }): ReactNode {
  const [draft, setDraft] = useState(() => draftOf(values, new Set(report.providers.map((one) => one.name))));
  const set = (part: Partial<Draft>): void => setDraft((was) => ({ ...was, ...part }));
  const speaking = draft.tts.vendor === "" ? report.speaks.vendor : draft.tts.vendor;
  const model = draft.tts.model === "" ? (draft.tts.vendor === "" ? report.speaks.model : null) : draft.tts.model;
  const apply = (next: TestValues | null): void => {
    if (next === null) setDraft(draftOf(null, new Set()));
    onApply(next);
    onClose();
  };

  return (
    <div className="set-test-body">
      <div className="set-test-rows">
        <StageRow modality="stt" icon="ear" label="Hears" running={report.hears} knob={draft.stt} report={report} own={own} onChange={(stt) => set({ stt })} />
        <StageRow modality="llm" icon="memory" label="Thinks" running={report.decides} knob={draft.llm} report={report} own={own} onChange={(llm) => set({ llm })} />
        <StageRow modality="tts" icon="speaker" label="Speaks" running={report.speaks} knob={draft.tts} report={report} own={own} onChange={(tts) => set({ tts, voice: "" })} />
        <div className="set-test-row">
          <span className="set-test-label">
            <Icon name="words" size={15} />
            Language
          </span>
          <Select value={draft.language} aria-label="Language" onValueChange={(language) => set({ language })} className="set-test-wide">
            <SelectItem value="">{report.speaks.language === null ? "Not set (current)" : `${languageSaid(report.speaks.language)} (current)`}</SelectItem>
            {languagesWith(draft.language).filter((tag) => tag !== report.speaks.language).map((tag) => (
              <SelectItem key={tag} value={tag}>
                {languageSaid(tag)}
              </SelectItem>
            ))}
          </Select>
        </div>
      </div>
      <VoiceField
        vendor={speaking}
        providers={report.providers}
        model={model}
        language={draft.language === "" ? report.speaks.language : draft.language}
        opening={report.greeting?.say ?? ""}
        voice={draft.voice === "" ? (report.speaks.voice_id ?? "") : draft.voice}
        onChange={(voice) => set({ voice })}
      />
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

/** One stage as a row: what it is, then its vendor and its model as two menus, each the agent's own until another is picked. */
function StageRow({ modality, icon, label, running, knob, report, own, onChange }: { modality: Modality; icon: IconName; label: string; running: Stage; knob: Knob; report: Report; own: ReadonlySet<string>; onChange: (knob: Knob) => void }): ReactNode {
  // The vendor running now is the first item, so it is not listed again under it.
  const ready = doing(report.providers, modality).filter((one: Provider) => one.ready && one.name !== running.vendor);
  const vendor = knob.vendor === "" ? running.vendor : knob.vendor;
  const known = report.models[`${modality}/${vendor}`] ?? [];
  const runsOn = report.runs[`${modality}/${vendor}`];
  const standing = knob.vendor === "" ? (running.model ?? runsOn) : runsOn;
  return (
    <div className="set-test-row">
      <span className="set-test-label">
        <Icon name={icon} size={15} />
        {label}
      </span>
      <Select value={knob.vendor} aria-label={`${label}: vendor`} onValueChange={(picked) => onChange({ vendor: picked, model: "" })}>
        <SelectItem value="">{brandOf(running.vendor)} (current)</SelectItem>
        {ready.map((one) => (
          <SelectItem key={one.name} value={one.name}>
            {brandOf(one.name)}
            {own.has(one.name) ? " · your API key" : ""}
          </SelectItem>
        ))}
      </Select>
      <Select value={knob.model} aria-label={`${label}: model`} disabled={known.length === 0} onValueChange={(picked) => onChange({ vendor: knob.vendor === "" && picked !== "" ? running.vendor : knob.vendor, model: picked })}>
        <SelectItem value="">{standing === undefined || standing === null ? "Default" : `${standing} (${knob.vendor === "" ? "current" : "default"})`}</SelectItem>
        {known.filter((name) => name !== standing).map((name) => (
          <SelectItem key={name} value={name}>
            {name}
          </SelectItem>
        ))}
      </Select>
    </div>
  );
}
