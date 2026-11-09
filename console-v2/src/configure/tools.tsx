/** A Studio agent's tools: the HTTPS requests the model may make during a call, the list beside the one open in its cards, tested before anything is saved. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { readSecrets } from "../apps/door";
import { readOnlyFor } from "./corner";
import { readStudioAgent, saveStudioAgent, type HttpTool, type StudioAgent } from "./door";
import { AuthCard, FixedCard, HeadersCard, MessagesCard, ParamsCard, SettingsCard } from "./tool-cards";
import { aTool, hostOf, replaced, toolRefused, without } from "./tool-shape";
import { TryPanel } from "./tool-try";
import "./tools.css";

function Editor({ agent, tool, others, secrets, readOnly, definition, onChange, onRemove }: { agent: string; tool: HttpTool; others: readonly HttpTool[]; secrets: readonly string[]; readOnly: boolean; definition: StudioAgent["definition"]; onChange: (tool: HttpTool) => void; onRemove: () => void }): ReactNode {
  const [testing, setTesting] = useState(false);
  const wrong = toolRefused(tool, others);
  return (
    <div className={testing ? "tl-editor tl-editor-testing" : "tl-editor"}>
      <div className="tl-cards">
        <div className="tl-editor-top">
          <span className="tl-editor-name tl-mono">{tool.name || "Unnamed"}</span>
          <div className="app-actions">
            {!readOnly && (
              <button type="button" className="app-button" aria-pressed={testing} onClick={() => setTesting((was) => !was)}>
                {testing ? "Close test" : "Test"}
              </button>
            )}
            {!readOnly && <ConfirmButton label="Delete" asks="Delete this tool?" danger onConfirm={onRemove} />}
          </div>
        </div>
        <SettingsCard tool={tool} readOnly={readOnly} wrong={wrong} onChange={onChange} />
        <ParamsCard params={tool.params} readOnly={readOnly} onChange={(params) => onChange({ ...tool, params })} />
        <FixedCard fixed={tool.fixed} readOnly={readOnly} onChange={(fixed) => onChange({ ...tool, fixed })} />
        <AuthCard tool={tool} secrets={secrets} readOnly={readOnly} onChange={(headers) => onChange({ ...tool, headers })} />
        <HeadersCard tool={tool} readOnly={readOnly} onChange={(headers) => onChange({ ...tool, headers })} />
        <MessagesCard tool={tool} readOnly={readOnly} onChange={onChange} />
      </div>
      {testing && <TryPanel key={tool.name} agent={agent} tool={tool} definition={definition} onClose={() => setTesting(false)} />}
    </div>
  );
}

export function StudioTools({ agent, kind, onSaved }: { agent: string; kind: "code" | "studio"; onSaved: () => void }): ReactNode {
  const credentials = useCredentials();
  const [read, setRead] = useState<StudioAgent | null>(null);
  const [tools, setTools] = useState<HttpTool[]>([]);
  const [open, setOpen] = useState(0);
  const [secrets, setSecrets] = useState<readonly string[]>([]);
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const readOnly = readOnlyFor(kind);

  useEffect(() => {
    let gone = false;
    readStudioAgent(credentials, agent).then(
      (answer) => {
        if (gone) return;
        setRead(answer);
        setTools(answer.definition.tools);
      },
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    readSecrets(credentials).then((held) => !gone && setSecrets(held.map((one) => one.name)), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  if (read === null) return refused === null ? <p className="dash-quiet">Reading its tools…</p> : <p className="cfg-refused">{refused}</p>;

  const dirty = JSON.stringify(tools) !== JSON.stringify(read.definition.tools);
  const invalid = tools.some((tool, at) => toolRefused(tool, without(tools, at)) !== null);
  const definition = { ...read.definition, tools };
  const current = tools[open];

  const change = (next: HttpTool[]): void => {
    setSaid(null);
    setTools(next);
  };
  const add = (): void => {
    change([...tools, aTool(tools)]);
    setOpen(tools.length);
  };
  const remove = (at: number): void => {
    change(without(tools, at));
    setOpen(Math.max(0, at - 1));
  };
  const save = async (): Promise<void> => {
    setSaving(true);
    setSaid(null);
    setRefused(null);
    try {
      const saved = await saveStudioAgent(credentials, agent, definition, read.release);
      setRead(saved);
      setTools(saved.definition.tools);
      setSaid(`Saved as release ${saved.release}`);
      onSaved();
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="tl">
      {!readOnly && (
        <div className="tl-top">
          <span className="dash-quiet" role="status">
            {said ?? (dirty ? "Unsaved changes" : "")}
          </span>
          <button type="button" className="cfg-save" disabled={!dirty || saving || invalid} onClick={() => void save()}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      )}
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      {tools.length === 0 ? (
        <section className="dash-card tl-empty">
          <h3 className="cfg-title">No tools yet</h3>
          <p className="dash-quiet">A tool is one HTTPS request to your own API, like looking up an order or booking a slot. The model decides when to make it and reads the answer.</p>
          {!readOnly && (
            <button type="button" className="app-button" onClick={add}>
              + New tool
            </button>
          )}
        </section>
      ) : (
        <div className="tl-layout">
          <nav className="tl-list" aria-label="Tools">
            {tools.map((tool, at) => (
              <button key={at} type="button" aria-current={at === open} className={at === open ? "tl-item tl-item-on" : "tl-item"} onClick={() => setOpen(at)}>
                <span className="dash-clip tl-item-name">{tool.name || "Unnamed"}</span>
                <span className="dash-clip tl-item-where">
                  <b>{tool.method}</b> {hostOf(tool.url)}
                </span>
              </button>
            ))}
            {!readOnly && (
              <button type="button" className="kn-add" onClick={add}>
                + New tool
              </button>
            )}
          </nav>
          {current !== undefined && <Editor key={open} agent={agent} tool={current} others={without(tools, open)} secrets={secrets} readOnly={readOnly} definition={definition} onChange={(next) => change(replaced(tools, open, next))} onRemove={() => remove(open)} />}
        </div>
      )}
    </div>
  );
}
