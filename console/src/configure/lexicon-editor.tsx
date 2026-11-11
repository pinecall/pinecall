/** The agent's lexicon, a row a word: how the voice says what it would get wrong, and the words the transcriber is told to expect. */

import { useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from "react";

import { EditDialog } from "./dialog";
import type { LexiconBody, Stage } from "./door";
import { ListenButton, useListen } from "./listen";
import { Locked } from "./stages";
import { Drop, More } from "./tool-cards";
import { replaced, without } from "./tool-shape";

type Said = LexiconBody["said"][number];

// The transcriber is told the first fifty: the runtime cuts the list there (session/hearing.py).
const MOST_HEARD = 50;
const BLANK: Said = { word: "", spoken: "" };

const filled = (one: Said): boolean => one.word.trim() !== "" || one.spoken.trim() !== "";
const half = (one: Said): boolean => filled(one) && (one.word.trim() === "" || one.spoken.trim() === "");

/** The written forms that appear twice, whatever their case: the voice finds a word in any case, so only one could win. */
function twice(said: readonly Said[]): Set<string> {
  const seen = new Set<string>();
  const again = new Set<string>();
  for (const one of said) {
    const word = one.word.trim().toLowerCase();
    if (word === "") continue;
    if (seen.has(word)) again.add(word);
    seen.add(word);
  }
  return again;
}

/** Words typed or pasted as a list: one a line, or separated by commas. */
const wordsOf = (text: string): string[] => text.split(/[\n,]/).map((word) => word.trim()).filter((word) => word !== "");

/** The voice a pronunciation is heard in: the agent's own, as its next call would say it; null where no voice is picked to ask for. */
export type Speaks = Stage & { voice_id: string };

function Pronunciations({ said, wrong, speaks, onChange }: { said: readonly Said[]; wrong: ReadonlySet<number>; speaks: Speaks | null; onChange: (said: Said[]) => void }): ReactNode {
  const { playing, refused, listen } = useListen();
  const hear = (at: number, spoken: string): void => {
    if (speaks !== null && playing === null) void listen(String(at), { tts: speaks.vendor, voice: speaks.voice_id, model: speaks.model, language: speaks.language, text: spoken });
  };
  const more = (): void => onChange([...said, BLANK]);
  // Enter in the last row opens the next one, so a list is typed without leaving the keyboard.
  const onEnter = (event: KeyboardEvent, at: number): void => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const row = said[at];
    if (at === said.length - 1 && row !== undefined && !half(row) && filled(row)) more();
  };
  return (
    <>
      {said.length > 0 && (
        <div className="cfg-lex-rows">
          <div className="cfg-lex-row cfg-lex-head" aria-hidden="true">
            <span>Written</span>
            <span />
            <span>Said as</span>
            <span />
          </div>
          {said.map((one, at) => (
            <div key={at} className={wrong.has(at) ? "cfg-lex-row cfg-lex-wrong" : "cfg-lex-row"}>
              <input className="cfg-input" aria-label="Written" placeholder="Nginx" spellCheck={false} autoFocus={at === said.length - 1 && !filled(one)} value={one.word} onChange={(event) => onChange(replaced(said, at, { ...one, word: event.target.value }))} onKeyDown={(event) => onEnter(event, at)} />
              <span className="cfg-lex-arrow" aria-hidden="true">
                →
              </span>
              <input className="cfg-input" aria-label="Said as" placeholder="engine x" spellCheck={false} value={one.spoken} onChange={(event) => onChange(replaced(said, at, { ...one, spoken: event.target.value }))} onKeyDown={(event) => onEnter(event, at)} />
              <ListenButton playing={playing === String(at)} label={speaks === null ? "Pick a voice for this agent to hear it" : `Hear “${one.spoken.trim()}” in the agent's voice`} disabled={speaks === null || one.spoken.trim() === ""} onClick={() => hear(at, one.spoken.trim())} />
              <Drop label={`Remove ${one.word || "pronunciation"}`} disabled={false} onClick={() => onChange(without(said, at))} />
            </div>
          ))}
        </div>
      )}
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      <More label="Add pronunciation" disabled={false} onClick={more} />
    </>
  );
}

function Heard({ heard, onChange }: { heard: readonly string[]; onChange: (heard: string[]) => void }): ReactNode {
  const [typed, setTyped] = useState("");
  const add = (words: readonly string[]): void => {
    const known = new Set(heard.map((word) => word.toLowerCase()));
    const fresh = words.filter((word) => !known.has(word.toLowerCase()) && known.add(word.toLowerCase()));
    if (fresh.length > 0) onChange([...heard, ...fresh]);
    setTyped("");
  };
  const onKey = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      add(wordsOf(typed));
    } else if (event.key === "Backspace" && typed === "" && heard.length > 0) {
      onChange(heard.slice(0, -1));
    }
  };
  // A list copied from a sheet or a document lands as its words, not as one long word.
  const onPaste = (event: ClipboardEvent): void => {
    const pasted = event.clipboardData.getData("text");
    if (!/[\n,]/.test(pasted)) return;
    event.preventDefault();
    add(wordsOf(`${typed}${pasted}`));
  };
  return (
    <div className="cfg-lex-words">
      {heard.map((word, at) => (
        <span key={`${at}-${word}`} className={at >= MOST_HEARD ? "cfg-lex-word cfg-lex-over" : "cfg-lex-word"}>
          {word}
          <Drop label={`Remove ${word}`} disabled={false} onClick={() => onChange(without(heard, at))} />
        </span>
      ))}
      <input className="cfg-lex-type" aria-label="A word to hear" placeholder={heard.length === 0 ? "Okonkwo, Brightside, Invisalign" : "Add a word"} spellCheck={false} value={typed} onChange={(event) => setTyped(event.target.value)} onKeyDown={onKey} onPaste={onPaste} onBlur={() => typed.trim() !== "" && add(wordsOf(typed))} />
    </div>
  );
}

function Part({ title, counted, about, locked, children }: { title: string; counted: string; about: string; locked: boolean; children: ReactNode }): ReactNode {
  return (
    <section className="cfg-lex" aria-label={title}>
      <div className="cfg-lex-top">
        <span className="ui-field-label">{title}</span>
        {locked ? <Locked /> : <span className="dash-quiet">{counted}</span>}
      </div>
      <p className="dash-quiet">{about}</p>
      {locked ? <p className="dash-quiet">The class declares these, and its words run whatever is kept here.</p> : children}
    </section>
  );
}

export function LexiconEditor({ lexicon, fixed, speaks, saving, refused, onClose, onSave }: { lexicon: LexiconBody; fixed: ReadonlySet<string>; speaks: Speaks | null; saving: boolean; refused: string | null; onClose: () => void; onSave: (lexicon: LexiconBody) => void }): ReactNode {
  // An empty lexicon opens on one blank row, ready to be typed in; a row left blank is never kept.
  const [said, setSaid] = useState<Said[]>(lexicon.said.length === 0 && !fixed.has("says") ? [BLANK] : lexicon.said);
  const [heard, setHeard] = useState<string[]>(lexicon.heard);
  const [wrong, setWrong] = useState<string | null>(null);
  const [marked, setMarked] = useState<ReadonlySet<number>>(new Set());

  const save = (): void => {
    const doubled = twice(said);
    const bad = new Set(said.flatMap((one, at) => (half(one) || doubled.has(one.word.trim().toLowerCase()) ? [at] : [])));
    setMarked(bad);
    if (said.some(half)) return setWrong("A pronunciation is a word and how it is said: fill both, or remove the row.");
    if (doubled.size > 0) return setWrong(`Written twice: ${[...doubled].join(", ")}. The voice finds a word in any case, so one row a word.`);
    setWrong(null);
    onSave({ said: said.filter(filled).map((one) => ({ word: one.word.trim(), spoken: one.spoken.trim() })), heard });
  };
  const changeSaid = (next: Said[]): void => {
    setSaid(next);
    setMarked(new Set());
  };
  const kept = said.filter(filled).length;

  return (
    <EditDialog title="Lexicon" icon="type" about="The words this agent must say right, and the ones it must hear right." saving={saving} refused={wrong ?? refused} onClose={onClose} onSave={save}>
      <Part title="Pronunciations" counted={kept === 0 ? "None" : String(kept)} about="Where the agent's answer has the word, the voice says it the other way: a whole word, in any case. The transcript keeps it as written. Play says it in the agent's voice." locked={fixed.has("says")}>
        <Pronunciations said={said} wrong={marked} speaks={speaks} onChange={changeSaid} />
      </Part>
      <Part title="Words to hear" counted={heard.length === 0 ? "None" : `${heard.length} of ${MOST_HEARD}`} about="Names the transcriber would mishear: surnames, brands, products. It is told to expect them on every call; a transcriber that takes no such list hears without them." locked={fixed.has("hears")}>
        <Heard heard={heard} onChange={setHeard} />
        {heard.length > MOST_HEARD && <p className="cfg-refused">Only the first {MOST_HEARD} reach the transcriber: the dimmed ones are kept and not sent.</p>}
      </Part>
    </EditDialog>
  );
}
