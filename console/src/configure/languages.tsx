/** The languages an agent's callers speak, picked by name, the main one first; and what its next call runs for them: the transcriber that hears them, the voice that speaks them, or why not. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Icon } from "../shell/icons";
import { Select, type SelectItem } from "../ui/select";
import { readReport, type Report, type Stage } from "./door";
import { brandOf } from "./vendors";

// The languages offered by name; any other is typed as its tag, and the gateway checks it with the vendors.
const TAGS: readonly string[] = ["en", "es", "pt", "fr", "de", "it", "nl", "ca", "sv", "da", "nb", "fi", "pl", "cs", "ro", "hu", "el", "tr", "ru", "uk", "ar", "he", "fa", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "id", "vi", "th", "ja", "ko", "zh"];
const NAMES = new Intl.DisplayNames(["en"], { type: "language" });
const OTHER = "other";
// Callers who mix their language with English are the usual reason for two: these are one click.
const PAIRS: readonly (readonly string[])[] = [["es", "en"], ["hi", "en"], ["ar", "en"], ["pt", "en"]];
// How long a pick waits before the gateway is asked what it would run: a person adding two asks once.
const ASKED_AFTER_MS = 250;

/** A tag's name in English ("es" is Spanish), or null for a tag this browser cannot name. */
export function languageName(tag: string): string | null {
  try {
    const name = NAMES.of(tag);
    return name === undefined || name.toLowerCase() === tag.toLowerCase() ? null : name;
  } catch {
    return null;
  }
}

/** The languages a setting names, each once, the main one first: "es, en" is Spanish and English. */
export function languagesIn(setting: string | null | undefined): string[] {
  return [...new Set((setting ?? "").split(",").map((one) => one.trim()).filter((one) => one !== ""))];
}

/** "Spanish", "Spanish and English", "Hindi, English and Tamil". */
export function languagesSaid(tags: readonly string[]): string {
  const names = tags.map((one) => languageName(one) ?? one);
  return names.length < 3 ? names.join(" and ") : `${names.slice(0, -1).join(", ")} and ${names.at(-1) ?? ""}`;
}

/** Every language offered by name, a row each: its name, its tag beside it, found by either. */
function languageItems(left: readonly string[]): SelectItem[] {
  return TAGS.filter((one) => !left.includes(one)).map((one) => ({ value: one, label: languageName(one) ?? one, tags: <span className="cfg-tag">{one}</span>, keywords: one }));
}

/** The languages picked, a chip each and the main one first, with a search that adds one and the pairs most callers mix. */
export function LanguagesPicker({ value, onChange }: { value: readonly string[]; onChange: (next: string[]) => void }): ReactNode {
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState("");
  const add = (tag: string): void => {
    if (tag === OTHER) return setTyping(true);
    if (tag !== "" && !value.includes(tag)) onChange([...value, tag]);
  };
  const addTyped = (): void => {
    add(typed.trim().toLowerCase());
    setTyped("");
    setTyping(false);
  };
  const items: SelectItem[] = [...languageItems(value), { value: OTHER, label: "Another language…", detail: "One not listed here, by its tag: gl, eu, sw." }];
  return (
    <div className="cfg-langs">
      {value.length > 0 && (
        <ul className="cfg-lang-chips" aria-label="Languages picked">
          {value.map((tag, at) => (
            <li key={tag} className="cfg-lang-chip">
              <span>{languageName(tag) ?? tag}</span>
              {at === 0 && value.length > 1 && <span className="cfg-tag">main</span>}
              <button type="button" className="cfg-lang-drop" aria-label={`Remove ${languageName(tag) ?? tag}`} onClick={() => onChange(value.filter((one) => one !== tag))}>
                <Icon name="close" size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Select items={items} value="" label="Add a language" placeholder={value.length === 0 ? "Pick the language your callers speak" : "Add another language they speak"} searchable searchPlaceholder="Search languages" onChange={add} />
      {typing && (
        <span className="cfg-lang-typed">
          <input className="cfg-input" aria-label="A language tag" value={typed} autoFocus spellCheck={false} placeholder="gl" onChange={(event) => setTyped(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (event.preventDefault(), addTyped())} />
          <button type="button" className="app-button" disabled={typed.trim() === ""} onClick={addTyped}>
            Add
          </button>
        </span>
      )}
      {value.length === 0 && (
        <span className="cfg-lang-pairs">
          <span className="dash-quiet">Callers who mix two:</span>
          {PAIRS.map((pair) => (
            <button key={pair.join()} type="button" className="pick-chip" onClick={() => onChange([...pair])}>
              {pair.map((one) => languageName(one) ?? one).join(" + ")}
            </button>
          ))}
        </span>
      )}
      {value.length > 1 && <span className="dash-quiet">The first is the main one: the greeting, the recording notice and the default voice are in it. A caller may speak any of them, and change in the middle of the call.</span>}
    </div>
  );
}

function modelOf(report: Report, stage: "stt" | "tts", running: Stage): string {
  const model = running.model ?? report.runs[`${stage}/${running.vendor}`] ?? null;
  return model === null ? brandOf(running.vendor) : `${brandOf(running.vendor)} ${model}`;
}

function Fit({ what, runs, takes, warn }: { what: string; runs: string; takes: string; warn: string | undefined }): ReactNode {
  return (
    <dd className={warn === undefined ? undefined : "cfg-fit-warn"}>
      <b>{what}.</b> {runs}
      {warn === undefined ? ` ${takes}` : ""}
      {warn !== undefined && <span className="cfg-set-warn">{warn}</span>}
    </dd>
  );
}

/** What the agent's next call would run if its callers spoke these: asked of the gateway as they are picked, nothing kept. */
export function LanguageFit({ agent, languages }: { agent: string; languages: readonly string[] }): ReactNode {
  const credentials = useCredentials();
  const [report, setReport] = useState<Report | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const asked = languages.join(",");

  useEffect(() => {
    let gone = false;
    const wait = window.setTimeout(() => {
      readReport(credentials, agent, asked === "" ? undefined : asked.split(",")).then(
        (read) => !gone && (setReport(read), setRefused(null)),
        (failed: unknown) => !gone && setRefused(saidBy(failed)),
      );
    }, ASKED_AFTER_MS);
    return () => {
      gone = true;
      window.clearTimeout(wait);
    };
  }, [credentials, agent, asked]);

  if (refused !== null) return <p className="cfg-refused">{refused}</p>;
  if (report === null) return <p className="dash-quiet">Reading what would run…</p>;
  const said = languages.length === 0 ? null : languagesSaid(languages);
  const listened = report.hears.languages.length === 0 ? "guesses among the languages it knows" : `listens for ${languagesSaid(report.hears.languages)}`;
  return (
    <dl className="cfg-reach">
      <dt>What runs</dt>
      <Fit what="The transcriber" runs={modelOf(report, "stt", report.hears)} takes={said === null ? listened : `hears ${said}.`} warn={report.warnings["hears"]} />
      <Fit what="The voice" runs={modelOf(report, "tts", report.speaks)} takes={said === null ? "speaks its own default language." : `speaks ${said}.`} warn={report.warnings["speaks"]} />
      {said !== null && (
        <dd>
          <b>The first words.</b> The recording notice and, on a call the agent places, who is calling are said in {languageName(languages[0] ?? "") ?? languages[0]}.
        </dd>
      )}
    </dl>
  );
}
