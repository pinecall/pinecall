/** Transcriber, Model, Voice: what each stage runs on, how it measured on the agent's calls, and the pencil that changes it — none where the class set it. */

import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Icon, type IconName } from "../shell/icons";
import { readVoices, type Report, type Stage, type TuningBody } from "./door";
import { JudgeEditor, StageEditor } from "./stage-editor";
import { brandOf, type Modality } from "./vendors";

export { brandOf, JudgeEditor, type Modality };


export function milliseconds(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 1000).toLocaleString("en-US")} ms`;
}

export function perMinute(value: number | null): string {
  return value === null ? "—" : `$${value.toFixed(3)}/min`;
}

export interface Measured {
  latency: number | null;
  cost: number | null;
}

export function Locked(): ReactNode {
  return <span className="cfg-locked">Set by the class</span>;
}

export function Pencil({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <button type="button" className="cfg-pencil" aria-label={label} title={label} onClick={onClick}>
      <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
      </svg>
    </button>
  );
}

function StageCard({ readOnly, eyebrow, icon, tone = "accent", title, under, facts, locked, onEdit }: { readOnly: boolean; eyebrow: string; icon: IconName; tone?: "accent" | "blue" | "pink"; title: string; under: string; facts: readonly { name: string; value: string }[]; locked: boolean; onEdit: () => void }): ReactNode {
  return (
    <div className={`cfg-stage cfg-tone-${tone}`}>
      <div className="cfg-stage-top">
        <span className="cfg-stage-mark" aria-hidden="true">
          <Icon name={icon} size={15} />
        </span>
        <span className="cfg-stage-kind">{eyebrow}</span>
        {locked ? <Locked /> : !readOnly && <Pencil label={`Change ${eyebrow.toLowerCase()}`} onClick={onEdit} />}
      </div>
      <span className="cfg-stage-title dash-clip">{title}</span>
      <span className="dash-quiet dash-clip">{under}</span>
      {facts.length > 0 && (
        <dl className="cfg-stage-facts">
          {facts.map((fact) => (
            <div key={fact.name}>
              <dt>{fact.name}</dt>
              <dd className="dash-clip">{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function modelOf(report: Report, modality: Modality, stage: Stage): string {
  return stage.model ?? report.runs[`${modality}/${stage.vendor}`] ?? `${brandOf(stage.vendor)}'s default`;
}

export function Stages({ readOnly, report, config, fixed, measured, saving, refused, onSave, onOpened, onKept }: { readOnly: boolean; report: Report; config: TuningBody; fixed: ReadonlySet<string>; measured: Readonly<Record<"hear" | "think" | "speak", Measured>>; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => Promise<boolean>; onOpened: () => void; onKept: () => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const [editing, setEditing] = useState<Modality | null>(null);
  const [voiceName, setVoiceName] = useState<string | null>(null);
  const { hears, decides, speaks } = report;
  const lists = report.providers.find((one) => one.name === speaks.vendor)?.voices_listed === true;
  const voice = speaks.voice_id ?? report.voice_defaults[`${speaks.vendor}/${speaks.language ?? ""}`] ?? null;

  useEffect(() => {
    let gone = false;
    setVoiceName(null);
    if (voice !== null && lists) {
      readVoices(credentials, speaks.vendor, speaks.language).then((read) => !gone && setVoiceName(read.find((one) => one.id === voice)?.name ?? null), () => undefined);
    }
    return () => {
      gone = true;
    };
  }, [credentials, voice, lists, speaks.vendor, speaks.language]);

  const open = (modality: Modality): void => {
    onOpened();
    setEditing(modality);
  };
  const shownVoice = voiceName ?? (voice === null ? "Default voice" : voice.length > 18 ? `${voice.slice(0, 8)}…` : voice);
  return (
    <>
      <div className="cfg-stages">
        <StageCard
          readOnly={readOnly}
          eyebrow="Transcriber"
          icon="ear"
          tone="accent"
          title={modelOf(report, "stt", hears)}
          under={[brandOf(hears.vendor), hears.language].filter((part) => part !== null).join(", ")}
          facts={[
            { name: "Latency", value: milliseconds(measured.hear.latency) },
            { name: "Cost", value: perMinute(measured.hear.cost) },
            { name: "Language", value: hears.language ?? "Auto" },
          ]}
          locked={fixed.has("stt")}
          onEdit={() => open("stt")}
        />
        <StageCard
          readOnly={readOnly}
          eyebrow="Model"
          icon="brain"
          tone="blue"
          title={modelOf(report, "llm", decides)}
          under={brandOf(decides.vendor)}
          facts={[
            { name: "Latency", value: milliseconds(measured.think.latency) },
            { name: "Cost", value: perMinute(measured.think.cost) },
            { name: "Temperature", value: config.temperature == null ? "Default" : String(config.temperature) },
          ]}
          locked={fixed.has("llm")}
          onEdit={() => open("llm")}
        />
        <StageCard
          readOnly={readOnly}
          eyebrow="Voice"
          icon="speaker"
          tone="pink"
          title={shownVoice}
          under={`${brandOf(speaks.vendor)}, ${modelOf(report, "tts", speaks)}`}
          facts={[
            { name: "Latency", value: milliseconds(measured.speak.latency) },
            { name: "Cost", value: perMinute(measured.speak.cost) },
            { name: "Language", value: speaks.language ?? "Auto" },
          ]}
          locked={fixed.has("voice")}
          onEdit={() => open("tts")}
        />
      </div>
      {editing !== null && (
        <StageEditor
          modality={editing}
          report={report}
          config={config}
          saving={saving}
          refused={refused}
          onSave={(changed, drop) => void onSave(changed, drop).then((done) => done && setEditing(null))}
          onClose={() => setEditing(null)}
          onKept={onKept}
        />
      )}
    </>
  );
}
