/** Lexicon screen: the agent's pronunciations and recognition words. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";

import { type LexiconAnswer, type LexiconBody, type LexiconRow } from "@pinecall/core/wire/rest-org";

import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { WORLD } from "../../lib/mode";
import { Button, Empty, Input, Page, PageHead, Refused, Segmented, Tabs } from "../../ui";
import { readLexicon, setLexicon } from "./door";
import "./lexicon.css";

function saidBy(failed: unknown): string {
  return failed instanceof Error ? failed.message : String(failed);
}

/** Editable form state: pronunciation pairs in order, and recognition words. */
interface Words {
  said: { word: string; spoken: string }[];
  heard: string[];
}

function wordsOf(row: LexiconRow | null): Words {
  return { said: [...(row?.lexicon.said ?? [])], heard: [...(row?.lexicon.heard ?? [])] };
}

type Tab = "said" | "heard";
type Corner = "yours" | "team";

/** Corner names used in the discard-changes prompt. */
const WHOSE: Record<Corner, string> = { yours: "your copy", team: "the team's" };

// Two tabs for two different fixes: the agent mispronounces a word, or mishears one.
const TABS: readonly { tab: Tab; name: string }[] = [
  { tab: "said", name: "Pronunciation" },
  { tab: "heard", name: "Recognition" },
];

// Editable with a supervisor key, no deploy needed. Production's console edits production's words;
// the sandbox's edits yours or the team's.
export function Lexicon(): ReactNode {
  const credentials = useCredentials();
  const agent = useParams()["agent"] ?? "";
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "heard" ? "heard" : "said";
  const [answer, setAnswer] = useState<LexiconAnswer | null>(null);
  const [words, setWords] = useState<Words>({ said: [], heard: [] });
  const [kept, setKept] = useState<Words>({ said: [], heard: [] });
  const [corner, setCorner] = useState<Corner>("yours");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [help, setHelp] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const production = WORLD === "production";

  const load = (read: LexiconAnswer, at: Corner): void => {
    const shown = wordsOf(production ? read.production : at === "team" ? read.team : (read.yours ?? read.team));
    setWords(shown);
    setKept(shown);
  };

  useEffect(() => {
    let gone = false;
    readLexicon(credentials, agent).then(
      (read) => {
        if (gone) return;
        setAnswer(read);
        load(read, "yours");
      },
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const standing = answer === null ? null : production ? answer.production : corner === "team" ? answer.team : answer.yours;
  const changed = JSON.stringify(words) !== JSON.stringify(kept);

  // Switching corners discards unsaved edits, and there is no history to recover them, so confirm first.
  const move = (picked: Corner): void => {
    if (picked === corner || answer === null) return;
    if (changed && !window.confirm(`Unsaved words in ${WHOSE[corner]}. Switching to ${WHOSE[picked]} discards them.`)) return;
    setCorner(picked);
    setSaid(null);
    load(answer, picked);
  };

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (answer === null) return;
    setSaving(true);
    setRefused(null);
    setSaid(null);
    const body: LexiconBody = { said: words.said, heard: words.heard };
    try {
      const read = await setLexicon(credentials, agent, body, standing?.version ?? null, note.trim() === "" ? null : note.trim(), corner === "team");
      setAnswer(read);
      load(read, corner);
      setNote("");
      setSaid(`Saved. ${agent} uses it from its next call.`);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page width={900} tight>
      <PageHead
        title="Lexicon"
        ledeWidth={640}
        lede={`${agent}'s own words: how the voice pronounces a brand, a surname or an acronym, and which names the speech recognition must expect. A change applies from its next call — no developer, no deploy.`}
      />

      {answer === null ? (
        <Empty>{refused ?? "Asking the gateway…"}</Empty>
      ) : (
        <form className="ui-card lex" onSubmit={(event) => void save(event)}>
          <div className="lex-where">
            {production ? (
              <span className="lex-where-words">Editing <b>production</b> — what customers hear.</span>
            ) : (
              <>
                <span className="lex-where-words">Editing</span>
                <Segmented
                  options={[
                    { value: "yours", label: "Your copy" },
                    { value: "team", label: "The team's" },
                  ]}
                  value={corner}
                  onChange={move}
                />
                <span className="lex-where-hint">
                  {corner === "yours" ? "Only your sandbox copy hears it." : "Every copy without words of its own hears it."}
                </span>
              </>
            )}
            <span className="lex-version">{standing === null ? "nothing saved yet" : `v${standing.version} · ${standing.author} · ${dayAndTime(standing.set_at)}`}</span>
          </div>

          <div className="lex-tabs">
            <Tabs
              label="Lexicon"
              tabs={TABS.map((one) => ({ ...one, mark: <span className="lex-count">{one.tab === "said" ? words.said.length : words.heard.length}</span> }))}
              on={tab}
              onPick={(picked) => setParams(picked === "said" ? {} : { tab: picked })}
            />
            <button type="button" className="lex-help" onClick={() => setHelp(true)}>
              How this works
            </button>
          </div>

          {answer.fixed.includes(tab === "said" ? "says" : "hears") ? (
            <section className="lex-panel">
              <p className="lex-none">Set by the class: these words are declared in the agent&apos;s code and win over the lexicon. Change them there, or take them out of the class to set them here.</p>
            </section>
          ) : tab === "said" ? (
            <Pronunciation words={words} onChange={setWords} />
          ) : (
            <Recognition words={words} onChange={setWords} />
          )}

          <div className="lex-save">
            <Input className="lex-note" value={note} placeholder="Why, for the history (optional)" aria-label="Why, for the history (optional)" onChange={(event) => setNote(event.target.value)} />
            <Button kind="primary" size="form" type="submit" disabled={saving || !changed}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
            <span className={changed ? "lex-state lex-state-dirty" : "lex-state"}>{changed ? "Unsaved changes" : (said ?? "Up to date")}</span>
          </div>
        </form>
      )}

      {help && <Help onClose={() => setHelp(false)} />}

      {/* Write refusals only; a read refusal is already shown in place of the screen. */}
      {answer !== null && <Refused>{refused}</Refused>}
    </Page>
  );
}

/** Help text for the two tabs, shown on demand. */
function Help({ onClose }: { onClose: () => void }): ReactNode {
  useEffect(() => {
    const key = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  return (
    <div className="lex-veil" onMouseDown={onClose}>
      <div className="lex-help-box" role="dialog" aria-label="How the lexicon works" onMouseDown={(event) => event.stopPropagation()}>
        <div className="lex-help-head">
          <b>How this works</b>
          <button type="button" className="lex-help-x" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>

        <section className="lex-help-part">
          <h3>Pronunciation</h3>
          <p>When the voice reads a word as it is written and gets it wrong, write it the way it should sound. The voice says the second spelling every time the first appears.</p>
          <p className="lex-help-eg">
            <b>Vidal</b> → “Bidal” · <b>SQL</b> → “sequel”
          </p>
        </section>

        <section className="lex-help-part">
          <h3>Recognition</h3>
          <p>Words a caller says that the speech recognition would otherwise mishear: brand names, surnames, streets, product codes. The agent's ears expect them on every call.</p>
          <p className="lex-help-eg">
            <b>Clínica Norte</b> · <b>Coral Gables</b> · <b>Ferrán</b>
          </p>
        </section>
      </div>
    </div>
  );
}

/** Pronunciation tab: written word and how the voice should say it. */
function Pronunciation({ words, onChange }: { words: Words; onChange: (words: Words) => void }): ReactNode {
  const [word, setWord] = useState("");
  const [spoken, setSpoken] = useState("");
  const add = (): void => {
    if (word.trim() === "" || spoken.trim() === "") return;
    onChange({ ...words, said: [...words.said.filter((one) => one.word !== word.trim()), { word: word.trim(), spoken: spoken.trim() }] });
    setWord("");
    setSpoken("");
  };
  return (
    <section className="lex-panel">
      {words.said.length === 0 ? (
        <p className="lex-none">No word is pronounced any other way than it is written.</p>
      ) : (
        <div className="lex-table">
          <div className="lex-row lex-row-head">
            <span>Written as</span>
            <span>Said as</span>
            <span />
          </div>
          {words.said.map((one) => (
            <div key={one.word} className="lex-row">
              <span className="lex-word">{one.word}</span>
              <span className="lex-spoken">“{one.spoken}”</span>
              <button type="button" className="lex-x" aria-label={`remove ${one.word}`} onClick={() => onChange({ ...words, said: words.said.filter((kept) => kept.word !== one.word) })}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="lex-add">
        <Input size="sm" value={word} placeholder="Written as — Vidal" aria-label="Written as" onChange={(event) => setWord(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (event.preventDefault(), add())} />
        <span className="lex-arrow" aria-hidden>
          →
        </span>
        <Input size="sm" value={spoken} placeholder="Said as — Bidal" aria-label="Said as" onChange={(event) => setSpoken(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (event.preventDefault(), add())} />
        <Button size="sm" disabled={word.trim() === "" || spoken.trim() === ""} onClick={add}>
          Add
        </Button>
      </div>
    </section>
  );
}

/** Recognition tab: words speech recognition would otherwise miss. */
function Recognition({ words, onChange }: { words: Words; onChange: (words: Words) => void }): ReactNode {
  const [hear, setHear] = useState("");
  const add = (): void => {
    const more = hear
      .split(/[,\n]/)
      .map((one) => one.trim())
      .filter((one) => one !== "" && !words.heard.includes(one));
    if (more.length > 0) onChange({ ...words, heard: [...words.heard, ...more] });
    setHear("");
  };
  return (
    <section className="lex-panel">
      {words.heard.length === 0 ? (
        <p className="lex-none">No extra words: the ears know only the names the call's state carries.</p>
      ) : (
        <div className="lex-chips">
          {words.heard.map((one) => (
            <span key={one} className="lex-chip">
              {one}
              <button type="button" className="lex-chip-x" aria-label={`remove ${one}`} onClick={() => onChange({ ...words, heard: words.heard.filter((kept) => kept !== one) })}>
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="lex-add">
        <Input size="sm" value={hear} placeholder="Add words — several at once, separated by commas" aria-label="Words the ears must expect" onChange={(event) => setHear(event.target.value)} onKeyDown={(event) => event.key === "Enter" && (event.preventDefault(), add())} />
        <Button size="sm" disabled={hear.trim() === ""} onClick={add}>
          Add
        </Button>
      </div>
    </section>
  );
}
