/** The dialog a stage is changed in: the vendor and the model as lists, the voice with a Listen, the stage's own knobs, and the vendor's options under them. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { EditDialog } from "./dialog";
import { keepProviderKey, readVoices, sampleOf, type ListedVoice, type ModelChoice, type Provider, type Report, type TuningBody } from "./door";
import { OptionsForm, type Options } from "./options-form";
import { brandOf, type Modality } from "./vendors";

const TITLES: Record<Modality, string> = { stt: "Transcriber", llm: "Model", tts: "Voice" };
const ENDS_THE_TURN: readonly { value: "" | "stt" | "livekit" | "smart-turn"; name: string; about: string }[] = [
  { value: "", name: "Default", about: "What the vendor's ears do best." },
  { value: "stt", name: "The ears", about: "The transcriber says when the caller is done." },
  { value: "smart-turn", name: "Smart Turn", about: "A local model listens for the end of the turn." },
  { value: "livekit", name: "LiveKit", about: "LiveKit's own detector." },
];

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

function Choice({ on, off = false, title, under, right, hint, onPick }: { on: boolean; off?: boolean; title: string; under?: ReactNode; right?: ReactNode; hint?: string | undefined; onPick: () => void }): ReactNode {
  return (
    <button type="button" role="option" aria-selected={on} aria-disabled={off} title={hint} className={on ? "pick pick-on" : off ? "pick pick-off" : "pick"} onClick={off ? undefined : onPick}>
      <span className="pick-words">
        <span className="dash-clip">{title}</span>
        {under !== undefined && under !== "" && <span className="dash-quiet dash-clip">{under}</span>}
      </span>
      {right}
    </button>
  );
}

/** `0.3` → "0.30", `2.5` → "2.50", `0.0001` → "0.0001": dollars with no more digits than they need. */
function dollars(value: number): string {
  if (value >= 1) return value.toFixed(2).replace(/\.?0+$/, "");
  return value.toFixed(value >= 0.01 ? 2 : 4).replace(/0+$/, "").replace(/\.$/, "");
}

/** What a model costs, in a few words: a thinking model per million tokens, ears and a voice per minute or per million characters. */
export function priceOf(price: ModelChoice["price"], modality: Modality): string | null {
  if (price === null || price === undefined) return null;
  if (modality === "llm" && price.input != null && price.output != null) return `$${dollars(price.input)} in · $${dollars(price.output)} out /1M tok`;
  if (price.audio_seconds != null) return `$${dollars(price.audio_seconds * 60)}/min`;
  if (price.minutes != null) return `$${dollars(price.minutes)}/min`;
  if (price.characters != null) return `$${dollars(price.characters * 1_000_000)}/1M chars`;
  if (price.input != null) return `$${dollars(price.input)}/1M tok`;
  return null;
}

/** Recommended first, then the rest the org may run, then the ones only its own key would run, each in the order they came. */
export function arranged(choices: readonly ModelChoice[]): ModelChoice[] {
  const rank = (one: ModelChoice): number => (one.recommended ? 0 : one.available ? 1 : 2);
  return [...choices].sort((a, b) => rank(a) - rank(b));
}

// Whose key a vendor would run on for this org, in the order the list shows them.
const WHOSE: Record<string, { rank: number; word: string }> = {
  yours: { rank: 0, word: "Your key" },
  offered: { rank: 1, word: "Pinecall's key" },
  "bring your own": { rank: 2, word: "Bring your key" },
  broken: { rank: 3, word: "Broken" },
};
const whose = (provider: Provider): { rank: number; word: string } => WHOSE[provider.availability ?? ""] ?? WHOSE["bring your own"]!;

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
      <span className="dash-quiet">{provider.availability === "offered" ? `Runs on Pinecall's ${brand} key. Yours runs it on your account and opens ${brand}'s own options.` : `Pinecall does not lend ${brand}: it runs on your key alone.`}</span>
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

/** Vendor and model, every vendor this runtime has for the stage as two lists side by side, with the key field under one that is not yet the org's. */
export function VendorModel({ report, modality, vendor, model, unset, onVendor, onModel, onKept }: { report: Report; modality: Modality; vendor: string; model: string; unset?: string; onVendor: (vendor: string) => void; onModel: (model: string) => void; onKept: () => Promise<void> }): ReactNode {
  const offered = report.providers.filter((one) => one.does.includes(modality)).sort((a, b) => whose(a).rank - whose(b).rank || a.name.localeCompare(b.name));
  const fallback = report.defaults[modality] ?? "";
  const running = vendor === "" ? fallback : vendor;
  const picked = vendor === "" ? undefined : offered.find((one) => one.name === vendor);
  // A runtime that answers no `choices` names the models the org may run alone, each as itself.
  const listed = report.choices[`${modality}/${running}`] ?? (report.models[`${modality}/${running}`] ?? []).map((one) => ({ model: one, name: one, recommended: false, available: true, price: null }));
  const known = model === "" || listed.some((one) => one.model === model) ? listed : [{ model, name: model, recommended: false, available: true, price: null }, ...listed];
  const models = arranged(known);
  const runs = report.runs[`${modality}/${running}`];
  const brand = brandOf(running);
  const [filter, setFilter] = useState("");
  const typed = filter.trim().toLowerCase();
  const shownModels = models.filter((one) => `${one.model} ${one.name}`.toLowerCase().includes(typed));
  return (
    <div className="pick-pair">
      <div className="pick-column">
        <span className="pick-head">Vendor</span>
        <div className="pick-list" role="listbox" aria-label="Vendor">
          <Choice on={vendor === ""} title={unset ?? "Pinecall's default"} under={unset === undefined && fallback !== "" ? brandOf(fallback) : undefined} onPick={() => onVendor("")} />
          {offered.map((one) => (
            <Choice key={one.name} on={vendor === one.name} title={brandOf(one.name)} under={whose(one).word} onPick={() => onVendor(one.name)} />
          ))}
        </div>
        {picked !== undefined && picked.availability !== "yours" && <KeyField key={picked.name} provider={picked} onKept={onKept} />}
      </div>
      <div className="pick-column">
        <span className="pick-head">
          Model
          {models.length > 8 && <input className="cfg-input pick-filter" aria-label="Search models" placeholder="Search" value={filter} onChange={(event) => setFilter(event.target.value)} />}
        </span>
        <div className="pick-list" role="listbox" aria-label="Model">
          <Choice on={model === ""} title={runs === undefined ? `${brand}'s default` : (listed.find((one) => one.model === runs)?.name ?? runs)} under={runs === undefined ? undefined : "Default"} onPick={() => onModel("")} />
          {shownModels.map((one) => {
            const price = priceOf(one.price, modality);
            return (
              <Choice
                key={one.model}
                on={model === one.model}
                off={!one.available}
                title={one.name}
                under={
                  <>
                    {one.name !== one.model && <span className="opt-mono">{one.model}</span>}
                    {one.name !== one.model && price !== null && " · "}
                    {price !== null && <span className="pick-stat">{price}</span>}
                  </>
                }
                right={one.recommended ? <span className="pick-badge">Recommended</span> : one.available ? undefined : <span className="pick-badge pick-badge-quiet">Your key</span>}
                hint={one.available ? undefined : `Pinecall does not lend ${brand}'s ${one.name}: add your ${brand} key to run it.`}
                onPick={() => onModel(one.model)}
              />
            );
          })}
          {models.length === 0 && <p className="dash-quiet cfg-voices-note">{brand} names its models inside its plugin.</p>}
        </div>
      </div>
    </div>
  );
}

function VoiceList({ vendor, model, language, voice, onVoice }: { vendor: string; model: string; language: string | null; voice: string; onVoice: (voice: string) => void }): ReactNode {
  const credentials = useCredentials();
  const [voices, setVoices] = useState<ListedVoice[] | null>(null);
  const [filter, setFilter] = useState("");
  const [gender, setGender] = useState("");
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

  const genders = [...new Set((voices ?? []).map((one) => one.gender).filter((one) => one !== ""))];
  const typed = filter.trim().toLowerCase();
  const shown = (voices ?? []).filter((one) => (gender === "" || one.gender === gender) && `${one.name} ${one.description} ${one.accent}`.toLowerCase().includes(typed)).slice(0, 80);
  return (
    <div className="pick-column">
      <span className="pick-head">
        Voice
        <span className="pick-tools">
          {genders.length > 1 && (
            <select className="cfg-input pick-filter" aria-label="Gender" value={gender} onChange={(event) => setGender(event.target.value)}>
              <option value="">Any</option>
              {genders.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          )}
          <input className="cfg-input pick-filter" aria-label="Search voices" placeholder="Search voices" value={filter} onChange={(event) => setFilter(event.target.value)} />
        </span>
      </span>
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      <div className="pick-list pick-voices" role="listbox" aria-label="Voice">
        <Choice on={voice === ""} title={`${brandOf(vendor)}'s default`} onPick={() => onVoice("")} />
        {voices === null && <p className="dash-quiet cfg-voices-note">Reading the voices…</p>}
        {voices !== null && shown.length === 0 && <p className="dash-quiet cfg-voices-note">No voice by that name.</p>}
        {shown.map((one) => (
          <Choice
            key={one.id}
            on={one.id === voice}
            title={one.name}
            under={[one.description, one.language, one.gender, one.accent].filter((part) => part !== "").join(" · ")}
            right={
              <span
                role="button"
                tabIndex={0}
                className={playing === one.id ? "pick-play pick-playing" : "pick-play"}
                aria-label={`Listen to ${one.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  if (playing === null) void listen(one.id);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    event.stopPropagation();
                    if (playing === null) void listen(one.id);
                  }
                }}
              >
                <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  {playing === one.id ? <path d="M6 5h4v14H6zM14 5h4v14h-4z" /> : <path d="M7 4v16l13-8z" />}
                </svg>
              </span>
            }
            onPick={() => onVoice(one.id)}
          />
        ))}
      </div>
    </div>
  );
}

function Temperature({ value, onChange }: { value: string; onChange: (value: string) => void }): ReactNode {
  return (
    <div className={value === "" ? "opt-row" : "opt-row opt-row-set"}>
      <span className="opt-row-name">
        <span className="opt-mono">temperature</span>
      </span>
      <span className="opt-slide">
        <input type="range" className="knob-range" min={0} max={2} step={0.05} aria-label="Temperature slider" value={value === "" ? 1 : Number(value)} onChange={(event) => onChange(event.target.value)} />
        <input className="cfg-input knob-number" type="number" min={0} max={2} step={0.1} aria-label="Temperature" placeholder="Default" value={value} onChange={(event) => onChange(event.target.value)} />
      </span>
    </div>
  );
}

function EndOfTurn({ value, onChange }: { value: string; onChange: (value: string) => void }): ReactNode {
  return (
    <div className="knob">
      <span className="pick-head">Who ends the caller's turn</span>
      <div className="knob-choices" role="radiogroup" aria-label="End of turn">
        {ENDS_THE_TURN.map((one) => (
          <button key={one.value} type="button" role="radio" aria-checked={value === one.value} className={value === one.value ? "pick pick-on" : "pick"} onClick={() => onChange(one.value)}>
            <span className="pick-words">
              <span>{one.name}</span>
              <span className="dash-quiet">{one.about}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function optionsOf(config: TuningBody, modality: Modality): Options {
  const held = config[`${modality}_options`];
  return held === null || held === undefined ? {} : { ...held };
}

/** Changing one stage: its vendor and model, its own knobs, the vendor's options; the rest of the corner's settings go back as they were. */
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

  return (
    <EditDialog title={TITLES[modality]} saving={saving} refused={refused} wide onSave={save} onClose={onClose}>
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
          <VoiceList vendor={running} model={model} language={report.speaks.language} voice={voice} onVoice={setVoice} />
        ) : (
          <label className="cfg-field">
            Voice id
            <input className="cfg-input" value={voice} spellCheck={false} placeholder={`${brandOf(running)}'s own default`} onChange={(event) => setVoice(event.target.value)} />
          </label>
        ))}
      {modality === "stt" && <EndOfTurn value={endOfTurn} onChange={setEndOfTurn} />}
      {running !== "" && <OptionsForm modality={modality} vendor={running} ownKey={ownKey} options={options} lead={modality === "llm" ? <Temperature value={temperature} onChange={setTemperature} /> : null} onChange={setOptions} />}
    </EditDialog>
  );
}

export function JudgeEditor({ report, config, saving, refused, onSave, onClose, onKept }: { report: Report; config: TuningBody; saving: boolean; refused: string | null; onSave: (changed: Partial<TuningBody>, drop?: readonly (keyof TuningBody)[]) => void; onClose: () => void; onKept: () => Promise<void> }): ReactNode {
  const first = splitWord(config.judge, report.providers);
  const [vendor, setVendor] = useState(first.vendor);
  const [model, setModel] = useState(first.model);
  return (
    <EditDialog
      title="Judge model"
      saving={saving}
      refused={refused}
      wide
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
        onKept={onKept}
      />
    </EditDialog>
  );
}
