/** Transcriber, Model, Voice: what each stage runs on, how it measured on the agent's calls, and the pencil that changes it — none where the class set it. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Icon, type IconName } from "../shell/icons";
import { EditDialog } from "./dialog";
import { readVoices, sampleOf, type ListedVoice, type Provider, type Report, type Stage, type TuningBody } from "./door";

export type Modality = "stt" | "llm" | "tts";

const BRANDS: Readonly<Record<string, string>> = { elevenlabs: "ElevenLabs", openai: "OpenAI", openrouter: "OpenRouter", xai: "xAI", assemblyai: "AssemblyAI" };

export function brandOf(name: string): string {
  return BRANDS[name] ?? `${name.charAt(0).toUpperCase()}${name.slice(1)}`;
}

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

function wordOf(vendor: string, model: string): string | undefined {
  if (vendor === "") return model === "" ? undefined : model;
  return model === "" ? vendor : `${vendor}/${model}`;
}

function splitWord(word: string | null | undefined, providers: readonly Provider[]): { vendor: string; model: string } {
  if (word === null || word === undefined || word === "") return { vendor: "", model: "" };
  const at = word.lastIndexOf("/");
  if (at >= 0) return { vendor: word.slice(0, at), model: word.slice(at + 1) };
  return providers.some((one) => one.name === word) ? { vendor: word, model: "" } : { vendor: "", model: word };
}

/** Vendor and model, from what this box can run. */
function VendorModel({ report, modality, vendor, model, unset, onVendor, onModel }: { report: Report; modality: Modality; vendor: string; model: string; unset?: string; onVendor: (vendor: string) => void; onModel: (model: string) => void }): ReactNode {
  const ready = report.providers.filter((one) => one.ready && one.does.includes(modality));
  const fallback = report.defaults[modality] ?? "";
  const running = vendor === "" ? fallback : vendor;
  const known = report.models[`${modality}/${running}`] ?? [];
  const models = model === "" || known.includes(model) ? known : [model, ...known];
  const runs = report.runs[`${modality}/${running}`];
  return (
    <>
      <label className="cfg-field">
        Vendor
        <select className="cfg-input" value={vendor} onChange={(event) => onVendor(event.target.value)}>
          <option value="">{unset ?? `Pinecall's default${fallback === "" ? "" : ` (${brandOf(fallback)})`}`}</option>
          {ready.map((one) => (
            <option key={one.name} value={one.name}>
              {brandOf(one.name)}
            </option>
          ))}
        </select>
      </label>
      <label className="cfg-field">
        Model
        <select className="cfg-input" value={model} disabled={models.length === 0} onChange={(event) => onModel(event.target.value)}>
          <option value="">{runs === undefined ? `${brandOf(running)}'s default` : `${runs} (default)`}</option>
          {models.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}

function VoiceList({ vendor, model, language, voice, onVoice }: { vendor: string; model: string; language: string | null; voice: string; onVoice: (voice: string) => void }): ReactNode {
  const credentials = useCredentials();
  const [voices, setVoices] = useState<ListedVoice[] | null>(null);
  const [filter, setFilter] = useState("");
  const [playing, setPlaying] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let gone = false;
    setVoices(null);
    readVoices(credentials, vendor, language).then((read) => !gone && setVoices(read), (failed: unknown) => !gone && setRefused(saidBy(failed)));
    return () => {
      gone = true;
      audio.current?.pause();
    };
  }, [credentials, vendor, language]);

  const listen = async (id: string): Promise<void> => {
    audio.current?.pause();
    setPlaying(id);
    setRefused(null);
    try {
      const url = await sampleOf(credentials, { tts: vendor, voice: id, model: model === "" ? null : model, language, text: null });
      const player = new Audio(url);
      audio.current = player;
      player.onended = () => {
        URL.revokeObjectURL(url);
        setPlaying(null);
      };
      await player.play();
    } catch (failed) {
      setPlaying(null);
      setRefused(saidBy(failed));
    }
  };

  const typed = filter.trim().toLowerCase();
  const shown = (voices ?? []).filter((one) => `${one.name} ${one.description} ${one.accent}`.toLowerCase().includes(typed)).slice(0, 60);
  return (
    <div className="cfg-field">
      Voice
      <input className="cfg-input" aria-label="Search voices" placeholder="Search voices" value={filter} onChange={(event) => setFilter(event.target.value)} />
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      <div className="cfg-voices">
        {voices === null && <p className="dash-quiet cfg-voices-note">Reading the voices…</p>}
        {voices !== null && shown.length === 0 && <p className="dash-quiet cfg-voices-note">No voice by that name.</p>}
        {shown.map((one) => (
          <div key={one.id} className={one.id === voice ? "cfg-voice cfg-voice-on" : "cfg-voice"}>
            <button type="button" className="cfg-voice-pick" aria-pressed={one.id === voice} onClick={() => onVoice(one.id)}>
              <span className="dash-clip">{one.name}</span>
              <span className="dash-quiet dash-clip">{[one.language, one.gender, one.accent].filter((part) => part !== "").join(", ")}</span>
            </button>
            <button type="button" className="app-button" disabled={playing !== null} onClick={() => void listen(one.id)}>
              {playing === one.id ? "Playing" : "Listen"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Changing one stage: the rest of the corner's settings go back as they were. */
function StageEditor({ title, modality, report, config, saving, refused, onSave, onClose }: { title: string; modality: Modality; report: Report; config: TuningBody; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => void; onClose: () => void }): ReactNode {
  const first = splitWord(config[modality], report.providers);
  const [vendor, setVendor] = useState(first.vendor);
  const [model, setModel] = useState(modality === "tts" && config.tts_model != null && config.tts_model !== "" ? config.tts_model : first.model);
  const [voice, setVoice] = useState(config.voice ?? "");
  const running = vendor === "" ? (report.defaults["tts"] ?? "") : vendor;
  const lists = report.providers.find((one) => one.name === running)?.voices_listed === true;
  const save = (): void => {
    const word = wordOf(vendor, model);
    const changed: Partial<TuningBody> = word === undefined ? {} : { [modality]: word };
    const dropped: (keyof TuningBody)[] = word === undefined ? [modality] : [];
    if (modality === "tts") {
      dropped.push("tts_model");
      if (voice.trim() === "") dropped.push("voice");
      else changed.voice = voice.trim();
    }
    onSave(changed, dropped);
  };
  return (
    <EditDialog title={title} saving={saving} refused={refused} wide={modality === "tts"} onSave={save} onClose={onClose}>
      <VendorModel
        report={report}
        modality={modality}
        vendor={vendor}
        model={model}
        onVendor={(next) => {
          setVendor(next);
          setModel("");
          setVoice("");
        }}
        onModel={setModel}
      />
      {modality === "tts" &&
        (lists ? (
          <VoiceList vendor={running} model={model} language={report.speaks.language} voice={voice} onVoice={setVoice} />
        ) : (
          <label className="cfg-field">
            Voice id
            <input className="cfg-input" value={voice} spellCheck={false} placeholder={`${brandOf(running)}'s own default`} onChange={(event) => setVoice(event.target.value)} />
          </label>
        ))}
    </EditDialog>
  );
}

export function JudgeEditor({ report, config, saving, refused, onSave, onClose }: { report: Report; config: TuningBody; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => void; onClose: () => void }): ReactNode {
  const first = splitWord(config.judge, report.providers);
  const [vendor, setVendor] = useState(first.vendor);
  const [model, setModel] = useState(first.model);
  return (
    <EditDialog
      title="Judge model"
      saving={saving}
      refused={refused}
      onSave={() => {
        const word = wordOf(vendor, model);
        if (word === undefined) onSave({}, ["judge"]);
        else onSave({ judge: word });
      }}
      onClose={onClose}
    >
      <VendorModel
        report={report}
        modality="llm"
        vendor={vendor}
        model={model}
        unset="The organization's choice"
        onVendor={(next) => {
          setVendor(next);
          setModel("");
        }}
        onModel={setModel}
      />
    </EditDialog>
  );
}

export function Stages({ readOnly, report, config, fixed, measured, saving, refused, onSave, onOpened }: { readOnly: boolean; report: Report; config: TuningBody; fixed: ReadonlySet<string>; measured: Readonly<Record<"hear" | "think" | "speak", Measured>>; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => Promise<boolean>; onOpened: () => void }): ReactNode {
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
          title={editing === "stt" ? "Transcriber" : editing === "llm" ? "Model" : "Voice"}
          modality={editing}
          report={report}
          config={config}
          saving={saving}
          refused={refused}
          onSave={(changed, drop) => void onSave(changed, drop).then((done) => done && setEditing(null))}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
