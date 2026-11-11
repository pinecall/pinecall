/** The panel a stage is changed in: the provider and the model as rich selects, the voice with a Listen, the stage's own settings and the vendor's. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { IconName } from "../shell/icons";
import { Select, type SelectItem } from "../ui/select";
import { Badge, Field, Mark, Setting, Slider } from "../ui/setting";
import { EditDialog } from "./dialog";
import { keepProviderKey, readVoices, type ListedVoice, type ModelChoice, type Provider, type Report, type TuningBody } from "./door";
import { ListenButton, useListen } from "./listen";
import { OptionsForm, type Options } from "./options-form";
import { brandOf, type Modality } from "./vendors";

const PANELS: Record<Modality, { title: string; icon: IconName; about: string }> = {
  stt: { title: "Transcriber Settings", icon: "ear", about: "Configure what turns the caller's voice into text, and when a turn is over." },
  llm: { title: "Model Settings", icon: "brain", about: "Configure the LLM that powers your assistant's intelligence, reasoning and conversation." },
  tts: { title: "Voice Settings", icon: "speaker", about: "Configure the voice your assistant speaks with." },
};
const ENDS_THE_TURN: readonly SelectItem[] = [
  { value: "", label: "Default", detail: "What the vendor's ears do best." },
  { value: "stt", label: "The ears", detail: "The transcriber says when the caller is done." },
  { value: "smart-turn", label: "Smart Turn", detail: "A local model listens for the end of the turn." },
  { value: "livekit", label: "LiveKit", detail: "LiveKit's own detector." },
];
// Whose key a vendor would run on for this org, in the order the list shows them.
const WHOSE: Record<string, { rank: number; word: string; group: string }> = {
  yours: { rank: 0, word: "Your key", group: "Your keys" },
  offered: { rank: 1, word: "Pinecall's key", group: "Lent by Pinecall" },
  "bring your own": { rank: 2, word: "Bring your key", group: "Needs your key" },
  broken: { rank: 3, word: "Broken", group: "Broken" },
};
const whose = (provider: Provider): { rank: number; word: string; group: string } => WHOSE[provider.availability ?? ""] ?? WHOSE["bring your own"]!;

export function wordOf(vendor: string, model: string): string | undefined {
  if (vendor === "") return model === "" ? undefined : model;
  return model === "" ? vendor : `${vendor}/${model}`;
}

export function splitWord(word: string | null | undefined, providers: readonly Provider[]): { vendor: string; model: string } {
  if (word === null || word === undefined || word === "") return { vendor: "", model: "" };
  const at = word.lastIndexOf("/");
  if (at >= 0) return { vendor: word.slice(0, at), model: word.slice(at + 1) };
  return providers.some((one) => one.name === word) ? { vendor: word, model: "" } : { vendor: "", model: word };
}

/** `0.3` → "0.30", `2` → "2", `0.0078` → "0.0078": dollars as a price list writes them. */
function dollars(value: number): string {
  if (value < 0.01) return String(Number(value.toPrecision(2)));
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

/** What a model costs, in a few words: a thinking model per million tokens, ears and a voice per minute or per million characters. */
function priceOf(price: ModelChoice["price"], modality: Modality): string | null {
  if (price === null || price === undefined) return null;
  if (modality === "llm" && price.input != null && price.output != null) return `$${dollars(price.input)} in · $${dollars(price.output)} out /1M tokens`;
  if (price.audio_seconds != null) return `$${dollars(price.audio_seconds * 60)}/min`;
  if (price.minutes != null) return `$${dollars(price.minutes)}/min`;
  if (price.characters != null) return `$${dollars(price.characters * 1_000_000)}/1M chars`;
  if (price.input != null) return `$${dollars(price.input)}/1M tokens`;
  return null;
}

/** The one that runs unpicked first, then the recommended, then the rest the org may run, then the ones only its own key would run. */
function arranged(choices: readonly ModelChoice[], runs: string | undefined): ModelChoice[] {
  const rank = (one: ModelChoice): number => (one.model === runs ? 0 : one.recommended ? 1 : one.available ? 2 : 3);
  return [...choices].sort((a, b) => rank(a) - rank(b));
}

/** The org's own key for the vendor picked, typed once: kept when the vendor takes it, and the list re-read so the vendor shows as yours. */
function KeyField({ provider, onKept }: { provider: Provider; onKept: () => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const [key, setKey] = useState("");
  const [keeping, setKeeping] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const brand = brandOf(provider.name);
  if (provider.availability === "broken") return <p className="cfg-refused">{provider.broken ?? `${brand}'s plugin is broken on this runtime.`}</p>;
  const keep = async (): Promise<void> => {
    if (key.trim() === "" || keeping) return;
    setKeeping(true);
    setRefused(null);
    try {
      await keepProviderKey(credentials, provider.name, key.trim());
      await onKept();
      setKey("");
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setKeeping(false);
    }
  };
  return (
    <div className="pick-key">
      <span className="opt-note">{provider.availability === "offered" ? `Runs on Pinecall's ${brand} key. Yours runs it on your account and opens every model and setting.` : `Pinecall does not lend ${brand}: it runs on your key alone.`}</span>
      <span className="pick-key-row">
        <input
          className="cfg-input"
          type="password"
          autoComplete="off"
          spellCheck={false}
          aria-label={`${brand} API key`}
          placeholder={`Your ${brand} API key`}
          value={key}
          disabled={keeping}
          onChange={(event) => setKey(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void keep();
            }
          }}
        />
        <button type="button" className="app-button" disabled={keeping || key.trim() === ""} onClick={() => void keep()}>
          {keeping ? "Trying it…" : "Add key"}
        </button>
      </span>
      {refused !== null && <p className="cfg-refused">{refused}</p>}
    </div>
  );
}

/** The provider and the model: every vendor this runtime has for the stage, the key field under one that is not yet the org's, its models the recommended first. */
export function VendorModel({ report, modality, vendor, model, unset, onVendor, onModel, onKept }: { report: Report; modality: Modality; vendor: string; model: string; unset?: string; onVendor: (vendor: string) => void; onModel: (model: string) => void; onKept: () => Promise<void> }): ReactNode {
  const offered = report.providers.filter((one) => one.does.includes(modality)).sort((a, b) => whose(a).rank - whose(b).rank || brandOf(a.name).localeCompare(brandOf(b.name)));
  const fallback = report.defaults[modality] ?? "";
  const running = vendor === "" ? fallback : vendor;
  const brand = brandOf(running);
  const picked = vendor === "" ? undefined : offered.find((one) => one.name === vendor);
  const runs = report.runs[`${modality}/${running}`];
  // A runtime that answers no `choices` names the models the org may run alone, each as itself.
  const listed = report.choices[`${modality}/${running}`] ?? (report.models[`${modality}/${running}`] ?? []).map((one) => ({ model: one, name: one, recommended: false, available: true, price: null }));
  const known = model === "" || listed.some((one) => one.model === model) ? listed : [{ model, name: model, recommended: false, available: true, price: null }, ...listed];

  const vendors: SelectItem[] = [
    { value: "", label: unset ?? "Pinecall's default", detail: unset === undefined && fallback !== "" ? brandOf(fallback) : undefined, leading: fallback === "" ? undefined : <Mark letter={brandOf(fallback).charAt(0)} /> },
    ...offered.map((one) => ({ value: one.name, label: brandOf(one.name), detail: whose(one).word, group: whose(one).group, keywords: one.name, leading: <Mark letter={brandOf(one.name).charAt(0)} />, disabled: one.availability === "broken", hint: one.broken ?? undefined })),
  ];
  const mark = <Mark letter={brand.charAt(0)} />;
  const models: SelectItem[] = arranged(known, runs).map((one) => {
    const isDefault = one.model === runs;
    const price = priceOf(one.price, modality);
    return {
      // The row that runs unpicked is the default: picking it leaves the model unpinned.
      value: isDefault ? "" : one.model,
      label: one.name,
      detail: [one.name === one.model ? null : one.model, price].filter((part) => part !== null).join(" · "),
      leading: mark,
      group: one.recommended ? "Recommended" : isDefault ? "Default" : one.available ? "Other models" : "Needs your key",
      keywords: one.model,
      disabled: !one.available,
      hint: one.available ? undefined : `Pinecall does not lend ${brand}'s ${one.name}: add your ${brand} key to run it.`,
      tags: isDefault ? <Badge quiet>Default</Badge> : undefined,
    };
  });
  if (runs === undefined || !known.some((one) => one.model === runs)) models.unshift({ value: "", label: runs ?? `${brand}'s default`, detail: "Default", leading: mark });

  return (
    <>
      <Field label="Provider">
        <Select items={vendors} value={vendor} label="Provider" searchPlaceholder="Search providers" onChange={onVendor} />
        {picked !== undefined && picked.availability !== "yours" && <KeyField key={picked.name} provider={picked} onKept={onKept} />}
      </Field>
      <Field label="Model">
        <Select items={models} value={model === runs ? "" : model} label="Model" placeholder={`${brand}'s default`} searchPlaceholder="Search models" onChange={onModel} />
      </Field>
    </>
  );
}

export function VoicePicker({ vendor, model, language, voice, onVoice }: { vendor: string; model: string; language: string | null; voice: string; onVoice: (voice: string) => void }): ReactNode {
  const credentials = useCredentials();
  const [voices, setVoices] = useState<ListedVoice[] | null>(null);
  const [gender, setGender] = useState("");
  const [unread, setUnread] = useState<string | null>(null);
  const { playing, refused: unheard, listen, stop } = useListen();
  const refused = unread ?? unheard;

  useEffect(() => {
    let gone = false;
    setVoices(null);
    readVoices(credentials, vendor, language).then((read) => !gone && setVoices(read), (failed: unknown) => !gone && setUnread(saidBy(failed)));
    return () => {
      gone = true;
      stop();
    };
  }, [credentials, vendor, language]);

  const all = voices ?? [];
  const genders = [...new Set(all.map((one) => one.gender).filter((one) => one !== ""))];
  const items: SelectItem[] = [
    { value: "", label: `${brandOf(vendor)}'s default` },
    // The voice in use stays listed whatever the filter, or the select would lose its name.
    ...all.filter((one) => gender === "" || one.gender === gender || one.id === voice).map((one) => ({
      value: one.id,
      label: one.name,
      detail: [one.description, one.language, one.gender, one.accent].filter((part) => part !== "").join(" · "),
      keywords: `${one.description} ${one.accent} ${one.language} ${one.gender}`,
      trailing: <ListenButton playing={playing === one.id} label={`Listen to ${one.name}`} onClick={() => playing === null && void listen(one.id, { tts: vendor, voice: one.id, model: model === "" ? null : model, language, text: null })} />,
    })),
  ];
  if (voice !== "" && voices !== null && !all.some((one) => one.id === voice)) items.splice(1, 0, { value: voice, label: voice });
  const filters = genders.length > 1 && (
    <div className="pick-chips">
      {["", ...genders].map((one) => (
        <button key={one} type="button" className={gender === one ? "pick-chip pick-chip-on" : "pick-chip"} onClick={() => setGender(one)}>
          {one === "" ? "Any" : one.charAt(0).toUpperCase() + one.slice(1)}
        </button>
      ))}
    </div>
  );
  return (
    <Field label="Voice">
      <Select items={items} value={voice} label="Voice" placeholder={voices === null ? "Reading the voices…" : "Choose a voice"} searchable searchPlaceholder="Search voices" head={filters} limit={120} onChange={onVoice} />
      {refused !== null && <p className="cfg-refused">{refused}</p>}
    </Field>
  );
}

function optionsOf(config: TuningBody, modality: Modality): Options {
  const held = config[`${modality}_options`];
  return held === null || held === undefined ? {} : { ...held };
}

/** Changing one stage: its vendor and model, its own settings, the vendor's; the rest of the corner's settings go back as they were. */
export function StageEditor({ modality, report, config, saving, refused, onSave, onClose, onKept }: { modality: Modality; report: Report; config: TuningBody; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop: readonly (keyof TuningBody)[]) => void; onClose: () => void; onKept: () => Promise<void> }): ReactNode {
  const first = splitWord(config[modality], report.providers);
  const [vendor, setVendor] = useState(first.vendor);
  const [model, setModel] = useState(modality === "tts" && config.tts_model != null && config.tts_model !== "" ? config.tts_model : first.model);
  const [voice, setVoice] = useState(config.voice ?? "");
  const [temperature, setTemperature] = useState(config.temperature == null ? "" : String(config.temperature));
  const [endOfTurn, setEndOfTurn] = useState<string>(config.end_of_turn ?? "");
  const [options, setOptions] = useState<Options>(optionsOf(config, modality));
  const running = vendor === "" ? (report.defaults[modality] ?? "") : vendor;
  const provider = report.providers.find((one) => one.name === running);
  const lists = provider?.voices_listed === true;
  const ownKey = provider?.availability === "yours";

  const save = (): void => {
    const word = wordOf(vendor, model);
    const changed: Partial<TuningBody> = word === undefined ? {} : { [modality]: word };
    const dropped: (keyof TuningBody)[] = word === undefined ? [modality] : [];
    if (modality === "tts") {
      dropped.push("tts_model");
      if (voice.trim() === "") dropped.push("voice");
      else changed.voice = voice.trim();
    }
    if (modality === "llm") {
      if (temperature.trim() === "") dropped.push("temperature");
      else changed.temperature = Number(temperature);
    }
    if (modality === "stt") {
      if (endOfTurn === "") dropped.push("end_of_turn");
      else changed.end_of_turn = endOfTurn as TuningBody["end_of_turn"];
    }
    const field = `${modality}_options` as const;
    if (Object.keys(options).length === 0) dropped.push(field);
    else changed[field] = options;
    onSave(changed, dropped);
  };

  const lead =
    modality === "llm" ? (
      <Setting icon="thermometer" title="Temperature" about="Controls randomness. Lower values are more deterministic, higher values more creative.">
        <Slider value={temperature} label="Temperature" min={0} max={2} step={0.05} rest={1} ends={["Precise", "Creative"]} onChange={setTemperature} />
      </Setting>
    ) : null;

  return (
    <EditDialog {...PANELS[modality]} saving={saving} refused={refused} onSave={save} onClose={onClose}>
      <VendorModel
        report={report}
        modality={modality}
        vendor={vendor}
        model={model}
        onVendor={(next) => {
          setVendor(next);
          setModel("");
          setVoice("");
          setOptions({});
        }}
        onModel={setModel}
        onKept={onKept}
      />
      {modality === "tts" &&
        (lists ? (
          <VoicePicker vendor={running} model={model} language={report.speaks.language} voice={voice} onVoice={setVoice} />
        ) : (
          <Field label="Voice id">
            <input className="cfg-input" aria-label="Voice id" value={voice} spellCheck={false} placeholder={`${brandOf(running)}'s own default`} onChange={(event) => setVoice(event.target.value)} />
          </Field>
        ))}
      {modality === "stt" && (
        <Setting icon="clock" title="End of turn" about="Who decides the caller is done speaking.">
          <Select items={ENDS_THE_TURN} value={endOfTurn} label="End of turn" searchable={false} onChange={setEndOfTurn} />
        </Setting>
      )}
      {running !== "" && <OptionsForm modality={modality} vendor={running} ownKey={ownKey} options={options} lead={lead} onChange={setOptions} />}
    </EditDialog>
  );
}

/** The judge of one agent; `unset` says what judges it when the agent names none: the organization's model, else Pinecall's. */
export function JudgeEditor({ report, config, unset, saving, refused, onSave, onClose, onKept }: { report: Report; config: TuningBody; unset: string; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => void; onClose: () => void; onKept: () => Promise<void> }): ReactNode {
  const first = splitWord(config.judge, report.providers);
  const [vendor, setVendor] = useState(first.vendor);
  const [model, setModel] = useState(first.model);
  return (
    <EditDialog
      title="Judge model"
      icon="judges"
      about="The model that grades this agent's calls."
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
        unset={unset}
        onVendor={(next) => {
          setVendor(next);
          setModel("");
        }}
        onModel={setModel}
        onKept={onKept}
      />
    </EditDialog>
  );
}
