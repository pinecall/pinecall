/** The Test panel of a Studio tool: the arguments typed, the real request sent once with the definition as the editor holds it, and what came back. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { tryTool, type HttpTool, type Param, type StudioAgent, type Tried } from "./door";

function pretty(body: unknown): string {
  if (body === null || body === undefined) return "(empty)";
  return typeof body === "string" ? body : JSON.stringify(body, null, 2);
}

function asSent(param: Param, typed: string | boolean | undefined): unknown {
  if (param.type === "boolean") return typed === true;
  if (typed === undefined || typed === "") return undefined;
  return param.type === "string" ? typed : Number(typed);
}

function Argument({ param, typed, onChange }: { param: Param; typed: string | boolean | undefined; onChange: (value: string | boolean) => void }): ReactNode {
  if (param.type === "boolean") {
    return (
      <label className="tl-check">
        <input type="checkbox" checked={typed === true} onChange={(event) => onChange(event.target.checked)} />
        {param.name}
      </label>
    );
  }
  const values = param.enum ?? [];
  return (
    <label className="tl-field">
      <span className="tl-field-top">
        <span className="tl-field-label tl-mono">{param.name}</span>
        {!param.required && <span className="dash-quiet">optional</span>}
      </span>
      {values.length > 0 ? (
        <select className="cfg-input" aria-label={param.name} value={String(typed ?? "")} onChange={(event) => onChange(event.target.value)}>
          <option value="">—</option>
          {values.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      ) : (
        <input className="cfg-input" type={param.type === "string" ? "text" : "number"} aria-label={param.name} placeholder={param.description || param.type} value={String(typed ?? "")} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

export function TryPanel({ agent, tool, definition, onClose }: { agent: string; tool: HttpTool; definition: StudioAgent["definition"]; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [typed, setTyped] = useState<Record<string, string | boolean>>({});
  const [tried, setTried] = useState<Tried | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const send = async (): Promise<void> => {
    const args: Record<string, unknown> = {};
    for (const param of tool.params) {
      const value = asSent(param, typed[param.name]);
      if (value !== undefined) args[param.name] = value;
    }
    setBusy(true);
    setRefused(null);
    try {
      setTried(await tryTool(credentials, agent, tool.name, args, definition));
    } catch (failed) {
      setTried(null);
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const bad = tried !== null && (tried.error !== null || tried.status === null || tried.status >= 400);
  return (
    <aside className="tl-try" aria-label={`Test ${tool.name}`}>
      <div className="tl-try-top">
        <span>
          <span className="tl-card-title">Test {tool.name}</span>
          <span className="dash-quiet tl-try-about">
            <b>{tool.method}</b> {tool.url.replace(/^https?:\/\//, "")}
          </span>
        </span>
        <button type="button" className="kn-drop" aria-label="Close" onClick={onClose}>
          ×
        </button>
      </div>
      <p className="dash-quiet">Sends the real request once, with what is on this page, saved or not. The answer is what the model would read.</p>
      {tool.params.length > 0 && (
        <div className="tl-args">
          {tool.params.map((param) => (
            <Argument key={param.name} param={param} typed={typed[param.name]} onChange={(value) => setTyped((was) => ({ ...was, [param.name]: value }))} />
          ))}
        </div>
      )}
      {tool.fixed.length > 0 && (
        <p className="dash-quiet">
          Also sent, fixed: {tool.fixed.map((field) => `${field.name}=${String(field.value)}`).join(", ")}
        </p>
      )}
      <div>
        <button type="button" className="cfg-save" disabled={busy} onClick={() => void send()}>
          {busy ? "Sending…" : "Send request"}
        </button>
      </div>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      {tried !== null && (
        <div className="tl-answer">
          <span className={bad ? "tl-status tl-status-bad" : "tl-status"}>
            {tried.status === null ? "No answer" : `HTTP ${tried.status}`} · {tried.duration_ms} ms
          </span>
          {tried.error !== null && <p className="cfg-refused">{tried.error}</p>}
          {(tried.body !== null && tried.body !== undefined) || tried.error === null ? <pre className="tl-body">{pretty(tried.body)}</pre> : null}
        </div>
      )}
    </aside>
  );
}
