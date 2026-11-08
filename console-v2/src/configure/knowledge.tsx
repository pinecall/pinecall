/** The Knowledge tab, edited where it is read: the bases the agent searches, new ones uploaded, what it always knows, and what it keeps of a caller. A switch or a row saves at once; a text saves on its button. */

import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";

import { read, saidBy, type Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { DocsConfig } from "@pinecall/core/wire/defs";
import { type KnowledgeBase, KnowledgeListSchema } from "@pinecall/core/wire/rest-retrieval";
import { ago } from "../lib/format";
import { cornerOf, readOnlyFor } from "./corner";
import { readSettings, setSettings, type TuningAnswer, type TuningBody } from "./door";
import { NewBase } from "./new-base";
import type { Save } from "./settings-list";
import { Locked } from "./stages";
import "./configure.css";
import "./knowledge.css";

async function readBases(credentials: Credentials): Promise<KnowledgeBase[]> {
  return KnowledgeListSchema.parse(await read(credentials, "/v1/knowledge")).bases;
}

type Mode = NonNullable<DocsConfig["mode"]>;

const MODES: readonly { value: Mode; name: string; says: string }[] = [
  { value: "retrieved", name: "Every turn", says: "Searched each time the caller finishes speaking." },
  { value: "tool", name: "When it decides", says: "The model searches only when it decides it needs to." },
];

interface Editing {
  readOnly: boolean;
  config: TuningBody;
  fixed: ReadonlySet<string>;
  saving: boolean;
  onSave: Save;
}

function Section({ title, about, locked, children }: { title: string; about: string; locked: boolean; children: ReactNode }): ReactNode {
  return (
    <section className="kn-section" aria-label={title}>
      <div className="kn-about">
        <h3 className="cfg-title">{title}</h3>
        <p className="dash-quiet">{about}</p>
        {locked && <Locked />}
      </div>
      <div className="kn-body">{children}</div>
    </section>
  );
}

function Toggle({ on, label, disabled, onChange }: { on: boolean; label: string; disabled: boolean; onChange: () => void }): ReactNode {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={on ? "kn-toggle kn-toggle-on" : "kn-toggle"} disabled={disabled} onClick={onChange}>
      <span className="kn-knob" aria-hidden="true" />
    </button>
  );
}

/** A number kept when the box is left or Enter is pressed; empty goes back to the default. */
function NumberField({ label, value, whole, disabled, onCommit }: { label: string; value: number | null | undefined; whole: boolean; disabled: boolean; onCommit: (value: number | null) => void }): ReactNode {
  const shown = value == null ? "" : String(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  const commit = (): void => {
    const trimmed = text.trim();
    const parsed = trimmed === "" ? null : Number(trimmed);
    if (parsed !== null && (Number.isNaN(parsed) || parsed < 0)) return setText(shown);
    const next = parsed === null || !whole ? parsed : Math.round(parsed);
    if (next !== (value ?? null)) onCommit(next);
  };
  return (
    <label className="kn-field">
      {label}
      <input className="cfg-input" inputMode={whole ? "numeric" : "decimal"} placeholder="Default" value={text} disabled={disabled} onChange={(event) => setText(event.target.value)} onBlur={commit} onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()} />
    </label>
  );
}

function BaseRow({ name, listed, used, disabled, onToggle, onChange }: { name: string; listed: KnowledgeBase | undefined; used: DocsConfig | undefined; disabled: boolean; onToggle: () => void; onChange: (next: Partial<DocsConfig>) => void }): ReactNode {
  const mode = used?.mode ?? "retrieved";
  return (
    <div className="kn-base">
      <div className="kn-base-top">
        <div className="kn-base-words">
          <span className="dash-clip kn-base-name">{name}</span>
          <span className="dash-quiet">{listed === undefined ? "No longer among this organization's bases" : `${listed.chunks.toLocaleString("en-US")} chunks, updated ${ago(listed.pushed_at)}`}</span>
        </div>
        <Toggle on={used !== undefined} label={`Use ${name}`} disabled={disabled} onChange={onToggle} />
      </div>
      {used !== undefined && (
        <div className="kn-base-how">
          <div className="kn-field">
            Searches
            <div className="dash-switch kn-modes" role="radiogroup" aria-label={`When ${name} is searched`}>
              {MODES.map((one) => (
                <button key={one.value} type="button" role="radio" aria-checked={mode === one.value} className={mode === one.value ? "dash-switch-on" : ""} disabled={disabled} onClick={() => mode !== one.value && onChange({ mode: one.value })}>
                  {one.name}
                </button>
              ))}
            </div>
            <span className="dash-quiet kn-mode-says">{MODES.find((one) => one.value === mode)?.says}</span>
          </div>
          <NumberField label="Results" value={used.k} whole disabled={disabled} onCommit={(k) => onChange({ k })} />
          <NumberField label="Minimum score" value={used.min_score} whole={false} disabled={disabled} onCommit={(min_score) => onChange({ min_score })} />
        </div>
      )}
    </div>
  );
}

function Bases({ readOnly, config, fixed, saving, onSave }: Editing): ReactNode {
  const credentials = useCredentials();
  const [bases, setBases] = useState<KnowledgeBase[] | null>(null);
  const [unread, setUnread] = useState<string | null>(null);
  const [making, setMaking] = useState(false);
  const attached = config.bases ?? [];
  const locked = fixed.has("docs");
  const disabled = locked || saving || readOnly;

  useEffect(() => {
    let gone = false;
    readBases(credentials).then((listed) => !gone && setBases(listed), (failed: unknown) => !gone && setUnread(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials]);

  const put = (next: readonly DocsConfig[]): void => void (next.length === 0 ? onSave({}, ["bases"]) : onSave({ bases: [...next] }));
  const names = [...new Set([...(bases ?? []).map((one) => one.base), ...attached.map((one) => one.base)])];

  // Made from this agent's page, so it starts in use here, unless its class decides what it reads.
  const made = (name: string): void => {
    setMaking(false);
    readBases(credentials).then(setBases, () => undefined);
    if (!locked) put([...attached, { base: name }]);
  };

  return (
    <Section title="Knowledge bases" about="Documents it can search to answer. Turn on the ones this agent should use, or upload new ones." locked={locked}>
      {locked ? (
        <p className="dash-quiet kn-none">Set by the class, in its code.</p>
      ) : (
        <>
      {unread !== null && <p className="cfg-refused">{unread}</p>}
      {bases === null && unread === null && <p className="dash-quiet">Reading the bases…</p>}
      {bases !== null && names.length === 0 && !making && <p className="dash-quiet kn-none">This organization has no knowledge base yet.</p>}
      {names.map((name) => {
        const used = attached.find((one) => one.base === name);
        return (
          <BaseRow
            key={name}
            name={name}
            listed={bases?.find((one) => one.base === name)}
            used={used}
            disabled={disabled}
            onToggle={() => put(used === undefined ? [...attached, { base: name }] : attached.filter((one) => one.base !== name))}
            onChange={(next) => put(attached.map((one) => (one.base === name ? { ...one, ...next } : one)))}
          />
        );
      })}
      {bases !== null &&
        !readOnly &&
        (making ? (
          <NewBase taken={names} using={!locked} onMade={made} onCancel={() => setMaking(false)} />
        ) : (
          <button type="button" className="kn-add" onClick={() => setMaking(true)}>
            + New knowledge base
          </button>
        ))}
        </>
      )}
    </Section>
  );
}

function AlwaysKnows({ readOnly, config, fixed, saving, onSave }: Editing): ReactNode {
  const kept = config.knowledge ?? "";
  const [text, setText] = useState(kept);
  const locked = fixed.has("knowledge");
  const dirty = text.trim() !== kept;
  return (
    <Section title="Always knows" about="Short facts it has in every call without searching: hours, address, policies." locked={locked}>
      {locked ? (
        <p className="dash-quiet kn-none">Set by the class, in its code.</p>
      ) : (
        <>
      <textarea className="cfg-input cfg-area kn-always" rows={6} placeholder={readOnly ? "Nothing set." : "We open Monday to Friday, 9 to 18."} value={text} readOnly={locked || readOnly} onChange={(event) => setText(event.target.value)} />
      <div className="kn-foot">
        <span className="dash-quiet">{text.trim().length.toLocaleString("en-US")} characters</span>
        {!locked && !readOnly && (
          <button type="button" className="cfg-save" disabled={!dirty || saving} onClick={() => void (text.trim() === "" ? onSave({}, ["knowledge"]) : onSave({ knowledge: text.trim() }))}>
            Save
          </button>
        )}
      </div>
        </>
      )}
    </Section>
  );
}

function Rules({ readOnly, title, placeholder, rows, disabled, onChange }: { readOnly: boolean; title: string; placeholder: string; rows: readonly string[]; disabled: boolean; onChange: (rows: string[]) => Promise<boolean> }): ReactNode {
  const [typed, setTyped] = useState("");
  const add = async (): Promise<void> => {
    const rule = typed.trim();
    if (rule === "" || disabled) return;
    if (rows.includes(rule)) return setTyped("");
    if (await onChange([...rows, rule])) setTyped("");
  };
  const enter = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    void add();
  };
  return (
    <div className="kn-rules">
      <span className="kn-rules-title">{title}</span>
      {rows.map((rule) => (
        <div key={rule} className="kn-rule">
          <span>{rule}</span>
          {!readOnly && (
            <button type="button" className="kn-drop" aria-label={`Remove ${rule}`} disabled={disabled} onClick={() => void onChange(rows.filter((one) => one !== rule))}>
              ×
            </button>
          )}
        </div>
      ))}
      {readOnly ? rows.length === 0 && <p className="dash-quiet">Nothing set.</p> : <input className="cfg-input" aria-label={`Add to ${title}`} placeholder={placeholder} value={typed} disabled={disabled} onChange={(event) => setTyped(event.target.value)} onKeyDown={enter} />}
    </div>
  );
}

function Memory({ readOnly, config, fixed, saving, onSave }: Editing): ReactNode {
  const remember = config.memory?.remember ?? [];
  const forget = config.memory?.forget ?? [];
  const locked = fixed.has("memory");
  const put = (keep: readonly string[], never: readonly string[]): Promise<boolean> => (keep.length === 0 && never.length === 0 ? onSave({}, ["memory"]) : onSave({ memory: { remember: [...keep], forget: [...never] } }));
  return (
    <Section title="Memory" about="What it keeps about a caller from one call to the next. Type one and press Enter." locked={locked}>
      {locked ? (
        <p className="dash-quiet kn-none">Set by the class, in its code.</p>
      ) : (
        <>
      <div className="kn-memory">
        <Rules readOnly={readOnly} title="Remembers" placeholder="The caller's name" rows={remember} disabled={locked || saving || readOnly} onChange={(rows) => put(rows, forget)} />
        <Rules readOnly={readOnly} title="Never keeps" placeholder="Card numbers" rows={forget} disabled={locked || saving || readOnly} onChange={(rows) => put(remember, rows)} />
      </div>
        </>
      )}
    </Section>
  );
}

export function KnowledgeTab({ agent, kind }: { agent: string; kind: "code" | "studio" }): ReactNode {
  const credentials = useCredentials();
  const [answer, setAnswer] = useState<TuningAnswer | null>(null);
  const team = false;
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [away, setAway] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readSettings(credentials, agent).then((settings) => !gone && setAnswer(settings), (failed: unknown) => !gone && setAway(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  if (away !== null) return <p className="cfg-refused">{away}</p>;
  if (answer === null) return <p className="dash-quiet">Reading what it knows…</p>;

  const corner = cornerOf(answer, team);
  const config: TuningBody = corner.inEffect?.config ?? {};

  // Only what was changed moves: every other setting goes back as the corner had it.
  const onSave: Save = async (changed, drop = []) => {
    setSaving(true);
    setSaved(false);
    setRefused(null);
    try {
      const next: TuningBody = { ...config, ...changed };
      for (const field of drop) delete next[field];
      setAnswer(await setSettings(credentials, agent, { config: next, if_version: corner.standing?.version ?? null, note: null, team }));
      setSaved(true);
      return true;
    } catch (failed) {
      setRefused(saidBy(failed));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const readOnly = readOnlyFor(kind);
  const editing: Editing = { readOnly, config, fixed: new Set(answer.fixed), saving, onSave };
  return (
    <div className="kn">
      {!readOnly && (
      <div className="kn-top">
        <span className="dash-quiet" role="status">
          {saving ? "Saving…" : saved ? "Saved" : ""}
        </span>
      </div>
      )}
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      <div key={team ? "team" : "yours"}>
        <Bases {...editing} />
        <AlwaysKnows {...editing} />
        <Memory {...editing} />
      </div>
    </div>
  );
}
