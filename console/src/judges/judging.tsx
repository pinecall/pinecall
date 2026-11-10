/** The org's judging, one button in the page's head: whether calls are judged at hang-up and on which model — Pinecall's, or one on the org's own key, never billed. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { EditDialog } from "../configure/dialog";
import { money } from "../lib/format";
import { Field, Setting, Toggle } from "../ui/setting";
import { readJudging, writeJudging, type JudgingSettings, type ModelConfig } from "./door";

const NOT_AN_OBJECT = 'The options are a JSON object: {"base_url": "http://your-gpu:8000/v1"}. Leave the field empty for none.';

// A model as one word, `vendor/model`: the model id keeps every slash after the vendor's.
function namedOf(model: ModelConfig | null | undefined): string {
  if (model === null || model === undefined) return "";
  return model.model === "" ? model.provider : `${model.provider}/${model.model}`;
}

function modelOf(named: string, options: string): ModelConfig | null {
  const word = named.trim();
  if (word === "") return null;
  const slash = word.indexOf("/");
  const model: ModelConfig = slash < 0 ? { provider: word, model: "" } : { provider: word.slice(0, slash), model: word.slice(slash + 1) };
  if (options.trim() === "") return model;
  let parsed: unknown;
  try {
    parsed = JSON.parse(options);
  } catch {
    throw new Error(NOT_AN_OBJECT);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(NOT_AN_OBJECT);
  return { ...model, options: parsed as Record<string, unknown> };
}

function billedOf(judging: JudgingSettings): string {
  if (judging.model !== null && judging.model !== undefined) return "On your own key, never billed.";
  return `${judging.ceiling_usd === null ? "Billed per eval" : `Billed per eval, at most ${money(judging.ceiling_usd)} a call`}. An answer of N/A is never billed.`;
}

function JudgingForm({ judging, onKept, onClose }: { judging: JudgingSettings; onKept: (kept: JudgingSettings) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [on, setOn] = useState(judging.on);
  const [named, setNamed] = useState(namedOf(judging.model));
  const [options, setOptions] = useState(judging.model?.options == null ? "" : JSON.stringify(judging.model.options, null, 2));
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  // The door takes both whole, so the switch and the model are saved together.
  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      onKept(await writeJudging(credentials, { on, model: modelOf(named, options) }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EditDialog title="Judging" icon="judges" about={`For the whole org, unless an agent names its own model. It holds from the next call. ${billedOf(judging)}`} saving={saving} refused={refused} onSave={() => void save()} onClose={onClose}>
      <Setting icon="judges" title="Judge calls at hang-up" about="Each active judge asks its one question of the whole call. Off, no judge is asked anything." aside={<Toggle on={on} label="Judge calls at hang-up" onChange={setOn} />} />
      <Field label="Model">
        <input className="cfg-input" aria-label="The judge model" placeholder="Pinecall's judge" spellCheck={false} value={named} onChange={(event) => setNamed(event.target.value)} />
        <span className="dash-quiet">
          Written <code>vendor/model</code>. Empty is Pinecall's own judge, billed per eval. A model on your org's own key for that vendor is never billed.
        </span>
      </Field>
      <Field label="On a server of your own">
        <textarea className="cfg-input cfg-area jd-options" aria-label="Plugin options" rows={3} spellCheck={false} placeholder='{ "base_url": "http://your-gpu:8000/v1" }' value={options} onChange={(event) => setOptions(event.target.value)} />
        <span className="dash-quiet">Options for the vendor's plugin, as JSON. The judge is asked for a tool call, so the model must call tools.</span>
      </Field>
    </EditDialog>
  );
}

export function Judging(): ReactNode {
  const credentials = useCredentials();
  const [judging, setJudging] = useState<JudgingSettings | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let gone = false;
    readJudging(credentials).then(
      (read) => !gone && setJudging(read),
      // A key that may not read the org's judging sees the judges without it.
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  if (judging === null) return null;

  return (
    <>
      <button type="button" className="app-button jd-judging" onClick={() => setEditing(true)}>
        <span className={judging.on ? "app-dot app-dot-good" : "app-dot app-dot-warn"} aria-hidden="true" />
        {judging.on ? "Judging on" : "Judging off"}
      </button>
      {editing && (
        <JudgingForm
          judging={judging}
          onKept={(kept) => {
            setJudging(kept);
            setEditing(false);
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  );
}
