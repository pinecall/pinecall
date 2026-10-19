/** A tool's Try box: one value per parameter, the request sent once with the definition as it stands, and what came back. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Check, Input, Refused } from "../../ui";
import { tryTool, type Definition, type HttpTool, type Param, type Tried } from "./door";

/** A typed value as the parameter's type sends it; an empty one is left out. */
function valueOf(param: Param, typed: string | boolean | undefined): unknown {
  if (param.type === "boolean") return typed === true;
  if (typed === undefined || typed === "") return undefined;
  if (param.type === "number" || param.type === "integer") return Number(typed);
  return typed;
}

export function TryBox({ agent, tool, definition }: { agent: string; tool: HttpTool; definition: Definition }): ReactNode {
  const credentials = useCredentials();
  const [typed, setTyped] = useState<Record<string, string | boolean>>({});
  const [tried, setTried] = useState<Tried | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const send = async (): Promise<void> => {
    const args: Record<string, unknown> = {};
    for (const param of tool.params) {
      const value = valueOf(param, typed[param.name]);
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

  return (
    <div className="sto-try">
      <div className="sto-try-head">
        <span className="sto-try-title">Try it</span>
        <span className="sto-hint">Sends this request once, as a call would, with what is on this page — saved or not.</span>
      </div>
      {tool.params.length > 0 && (
        <div className="sto-try-args">
          {tool.params.map((param) =>
            param.type === "boolean" ? (
              <Check key={param.name} checked={typed[param.name] === true} onChange={(on) => setTyped((was) => ({ ...was, [param.name]: on }))}>
                {param.name || "(unnamed)"}
              </Check>
            ) : (
              <Input
                key={param.name}
                size="sm"
                type={param.type === "string" ? "text" : "number"}
                value={String(typed[param.name] ?? "")}
                placeholder={param.name || "(unnamed)"}
                aria-label={param.name}
                onChange={(event) => setTyped((was) => ({ ...was, [param.name]: event.target.value }))}
              />
            ),
          )}
        </div>
      )}
      <div>
        <Button size="sm" kind="primary" disabled={busy} onClick={() => void send()}>
          {busy ? "Trying…" : "Try"}
        </Button>
      </div>
      <Refused>{refused}</Refused>
      {tried !== null && <Answer tried={tried} />}
    </div>
  );
}

function Answer({ tried }: { tried: Tried }): ReactNode {
  const failed = tried.error !== null || tried.status === null || tried.status >= 400;
  return (
    <div className="sto-try-answer">
      <div className={failed ? "sto-try-status sto-try-status-bad" : "sto-try-status"}>
        {tried.status === null ? "No answer" : `HTTP ${tried.status}`} · {tried.duration_ms} ms
      </div>
      {tried.error !== null ? <p className="sto-try-error">{tried.error}</p> : <pre className="ui-code sto-try-body">{pretty(tried.body)}</pre>}
    </div>
  );
}

function pretty(body: unknown): string {
  if (body === null || body === undefined) return "(empty)";
  return typeof body === "string" ? body : JSON.stringify(body, null, 2);
}
