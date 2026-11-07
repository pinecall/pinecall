/** The voice picked by ear: the vendor's voices in the agent's language, each played saying the agent's own words, with the wait before it starts. */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Icon, Input, Label, Segmented, Select, SelectItem } from "../../ui";
import { VoiceById } from "./voice-by-id";
import { brandOf } from "../../lib/catalogue";
import { heard, readVoices, type Heard, type ListedVoice } from "./voice-doors";

type Gender = "any" | "feminine" | "masculine";
const GENDERS: readonly { value: Gender; label: string }[] = [
  { value: "any", label: "Any" },
  { value: "feminine", label: "Female" },
  { value: "masculine", label: "Male" },
];

const regions = new Intl.DisplayNames(["en"], { type: "region" });

/** A country code as a person reads it: `ES` is Spain. */
function countryName(code: string): string {
  try {
    return regions.of(code) ?? code;
  } catch {
    return code;
  }
}

/** Every country the voices are from, the one with the most voices first. */
export function countriesOf(voices: readonly ListedVoice[]): string[] {
  const counted = new Map<string, number>();
  for (const voice of voices) if (voice.country !== "") counted.set(voice.country, (counted.get(voice.country) ?? 0) + 1);
  return [...counted.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([code]) => code);
}

/** The voices a person is looking at: by country, by gender, by a word of the name or description. */
export function narrowed(voices: readonly ListedVoice[], country: string, gender: Gender, words: string): ListedVoice[] {
  const wanted = words.trim().toLowerCase();
  return voices.filter(
    (voice) =>
      (country === "" || voice.country === country) &&
      (gender === "any" || voice.gender === gender) &&
      (wanted === "" || `${voice.name} ${voice.description}`.toLowerCase().includes(wanted)),
  );
}

/** The voice a call speaks on this vendor when none is picked: the providers row's for the language, else none named. */
export function unpickedVoice(defaults: Readonly<Record<string, string>>, vendor: string | null, language: string | null): string | null {
  if (vendor === null || language === null) return null;
  return defaults[`${vendor}/${language.split("-")[0]?.toLowerCase() ?? ""}`] ?? null;
}

export function VoicePicker({
  vendor,
  model,
  language,
  opening,
  voice,
  unpicked,
  onChange,
}: {
  vendor: string;
  /** The model a call would speak with: the one picked above, or null for the vendor's default. */
  model: string | null;
  language: string | null;
  /** The agent's own opening, which is what each voice says when it has one. */
  opening: string;
  voice: string;
  /** The voice a call speaks when none is picked, where the providers row names one; undefined where the picker is that default itself (the operator's row). */
  unpicked?: string | null | undefined;
  onChange: (voice: string) => void;
}): ReactNode {
  const credentials = useCredentials();
  const [voices, setVoices] = useState<ListedVoice[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [country, setCountry] = useState("");
  const [gender, setGender] = useState<Gender>("any");
  const [words, setWords] = useState("");
  const [text, setText] = useState(opening.trim());
  const [playing, setPlaying] = useState<string | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  // A sample is seconds of a vendor's time: each voice is asked once per vendor, model and line
  // and kept while those three stand, so playing a voice again costs nothing. The line each row
  // shows its wait beside is the one it was asked with — the key says so.
  const [samples, setSamples] = useState<ReadonlyMap<string, Heard>>(new Map());
  const held = useRef(samples);
  const player = useRef<HTMLAudioElement | null>(null);
  const gone = useRef(false);
  const said = text.trim();
  const keyFor = (id: string): string => `${vendor}\n${model ?? ""}\n${said}\n${id}`;

  useEffect(() => {
    held.current = samples;
  }, [samples]);

  useEffect(() => {
    let stale = false;
    setVoices(null);
    setRefused(null);
    readVoices(credentials, vendor, language).then(
      (read) => !stale && setVoices(read),
      (failed: unknown) => !stale && setRefused(saidBy(failed)),
    );
    return () => {
      stale = true;
    };
  }, [credentials, vendor, language]);

  // A blob URL is memory until it is revoked: the samples of a line no longer on screen go when
  // the line, the model or the vendor changes, and all of them when the picker closes.
  useEffect(() => {
    setSamples((before) => (before.size === 0 ? before : new Map()));
    return () => {
      player.current?.pause();
      setPlaying(null);
      for (const sample of held.current.values()) URL.revokeObjectURL(sample.url);
    };
  }, [vendor, model, said]);

  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
    };
  }, []);

  const countries = useMemo(() => countriesOf(voices ?? []), [voices]);
  // ElevenLabs' curated names carry no gender, so a picker over them offers no gender to pick.
  const gendered = useMemo(() => (voices ?? []).some((one) => one.gender !== ""), [voices]);
  const shown = useMemo(() => narrowed(voices ?? [], country, gendered ? gender : "any", words), [voices, country, gendered, gender, words]);
  // What a caller hears: the voice picked, else the row's default for the language, else the model's own.
  const speaking = voice !== "" ? voice : (unpicked ?? null);
  const inUse = voices?.find((one) => one.id === speaking);

  const play = async (id: string): Promise<void> => {
    player.current?.pause();
    if (playing === id) {
      setPlaying(null);
      return;
    }
    let sample = samples.get(keyFor(id));
    if (sample === undefined) {
      setAsking(id);
      setRefused(null);
      try {
        // No line of the person's own is no `text`: the gateway reads one in the agent's language.
        sample = await heard(credentials, { tts: vendor, voice: id, model, language, ...(said === "" ? {} : { text: said }) });
      } catch (failed) {
        if (!gone.current) setRefused(saidBy(failed));
        return;
      } finally {
        if (!gone.current) setAsking(null);
      }
      if (gone.current) {
        URL.revokeObjectURL(sample.url);
        return;
      }
      const kept = sample;
      setSamples((before) => new Map(before).set(keyFor(id), kept));
    }
    const audio = new Audio(sample.url);
    player.current = audio;
    audio.onended = () => setPlaying((now) => (now === id ? null : now));
    audio.onerror = () => setPlaying((now) => (now === id ? null : now));
    setPlaying(id);
    try {
      await audio.play();
    } catch (failed) {
      // A browser that wants a gesture it did not get, or a WAV it cannot decode: the row must not
      // stay on "stop" for a sound nobody hears.
      setPlaying(null);
      setRefused(saidBy(failed));
    }
  };

  const waitOf = (id: string): string => {
    if (asking === id) return "…";
    const wait = samples.get(keyFor(id))?.firstAudioMs;
    return wait === undefined || wait === null ? "" : `${wait} ms`;
  };

  return (
    <div className="set-voices">
      <div className="set-voices-now">
        <span className="set-voices-icon" aria-hidden>
          <Icon name="speaker" size={16} />
        </span>
        <span className="set-voices-said">
          <span className="set-voices-label">Speaking as</span>
          <span className="set-voices-in-use">
            {speaking === null ? `${brandOf(vendor)}'s own voice` : inUse !== undefined ? inUse.name : speaking}
            {voice === "" && <span className="set-voices-default">{speaking === null ? "nothing picked" : "the default"}</span>}
          </span>
        </span>
        {voice !== "" && unpicked !== undefined && (
          <Button size="sm" onClick={() => onChange("")}>
            Back to the default
          </Button>
        )}
      </div>
      <div className="set-voices-filters">
        <Input value={words} placeholder="Search voices" aria-label="Search voices" onChange={(event) => setWords(event.target.value)} />
        {countries.length > 1 && (
          <Select value={country} aria-label="Country" onValueChange={(value) => setCountry(value)}>
            <SelectItem value="">Every country</SelectItem>
            {countries.map((code) => (
              <SelectItem key={code} value={code}>
                {countryName(code)}
              </SelectItem>
            ))}
          </Select>
        )}
        {gendered && <Segmented options={GENDERS} value={gender} onChange={setGender} />}
      </div>
      <div className="set-voices-line">
        <Label>Try them with your own words</Label>
        <Input value={text} placeholder="Leave it empty to hear a line in the agent's language" aria-label="What each voice says" onChange={(event) => setText(event.target.value)} />
      </div>
      {refused !== null && <p className="set-help set-voices-refused">{refused}</p>}
      {voices === null && refused === null && <p className="set-help">Asking {vendor} for its voices…</p>}
      {voices !== null && (
        <ul className="set-voices-list" aria-label="Voices">
          {shown.map((one) => (
            <li key={one.id} className={one.id === speaking ? "set-voice on" : "set-voice"}>
              <button
                type="button"
                className="set-voice-play"
                aria-label={playing === one.id ? `Stop ${one.name}` : `Play ${one.name}`}
                aria-pressed={playing === one.id}
                disabled={asking !== null && asking !== one.id}
                onClick={() => void play(one.id)}
              >
                <Icon name={playing === one.id ? "stop" : "play"} size={14} />
              </button>
              <span className="set-voice-name">
                {one.name}
                <span className="set-voice-about">{[one.gender === "feminine" ? "female" : one.gender === "masculine" ? "male" : "", one.country === "" ? "" : countryName(one.country), one.accent].filter((word) => word !== "").join(" · ")}</span>
              </span>
              <span className="set-voice-wait">{waitOf(one.id)}</span>
              {one.id === speaking ? (
                <span className="set-voice-chosen">
                  <Icon name="tick" size={12} />
                  {voice === "" ? "Default" : "In use"}
                </span>
              ) : (
                <Button size="xs" onClick={() => onChange(one.id)}>
                  Use
                </Button>
              )}
            </li>
          ))}
          {shown.length === 0 && <li className="set-help">No voice matches.</li>}
        </ul>
      )}
      <VoiceById vendor={vendor} model={model} language={language} opening={said} voice={voice} onChange={onChange} label="Or a voice by its id — your own, or a clone" />
      <p className="set-help">Press play to hear each voice as a caller would; the number is how long it took to start talking. Nothing changes until you save.</p>
    </div>
  );
}
