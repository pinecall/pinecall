/** What the numbers' forms share: one request at a time with its refusal, the plan read before a write, the agent that answers, a value to copy, and a number's path. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { readPath, type NumberPath, type Wired } from "./door";

export interface Mover {
  busy: boolean;
  refused: string | null;
  /** Runs one request, says why it was refused, and throws on so the caller stops there. */
  move: <Answer>(work: () => Promise<Answer>) => Promise<Answer>;
}

export function useMove(): Mover {
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const move = useCallback(async <Answer,>(work: () => Promise<Answer>): Promise<Answer> => {
    setBusy(true);
    setRefused(null);
    try {
      return await work();
    } catch (failed) {
      setRefused(saidBy(failed));
      throw failed;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, refused, move };
}

/** The gateway's own steps, one a line: the first word is what each is done on. */
export function Steps({ steps }: { steps: readonly string[] }): ReactNode {
  return (
    <ol className="num-steps">
      {steps.map((step, at) => {
        const cut = step.indexOf(":");
        return (
          <li key={at}>
            {cut === -1 ? (
              step
            ) : (
              <>
                <b>{step.slice(0, cut)}</b>
                {step.slice(cut + 1)}
              </>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** What will happen, read before anything is written, and the button that does it. */
export function Plan({ plan, busy, confirm, onConfirm, onBack }: { plan: Wired; busy: boolean; confirm: string; onConfirm: () => void; onBack: () => void }): ReactNode {
  return (
    <div className="num-plan">
      <span className="num-plan-title">What will happen. Nothing is changed until you confirm.</span>
      <Steps steps={plan.steps} />
      <div className="cfg-dialog-foot">
        <button type="button" className="app-button" disabled={busy} onClick={onBack}>
          Back
        </button>
        <button type="button" className="cfg-save" disabled={busy} onClick={onConfirm}>
          {busy ? "Working…" : confirm}
        </button>
      </div>
    </div>
  );
}

/** The agent that picks up: chosen among the org's, or said when the form was opened for one. */
export function AgentField({ agents, fixed, value, onChange }: { agents: readonly string[]; fixed: boolean; value: string; onChange: (agent: string) => void }): ReactNode {
  if (fixed) return null;
  return (
    <Field label="Agent that picks up">
      {agents.length === 0 ? <p className="dash-quiet">No agent yet. Make one first, then give it a number.</p> : <Select label="Agent that picks up" items={agents.map((one) => ({ value: one, label: one }))} value={value} onChange={onChange} />}
    </Field>
  );
}

/** A value and the way to copy it; `bare`, the way is a small icon. */
export function Copy({ text, bare = false }: { text: string; bare?: boolean }): ReactNode {
  const [copied, setCopied] = useState(false);
  const copy = (): void => void navigator.clipboard.writeText(text).then(() => (setCopied(true), window.setTimeout(() => setCopied(false), 1400)), () => undefined);
  return (
    <span className="num-copy">
      <code>{text}</code>
      {bare ? (
        <button type="button" className="tst-x" aria-label={`Copy ${text}`} title={copied ? "Copied" : "Copy"} onClick={copy}>
          <Icon name={copied ? "check" : "copy"} size={13} />
        </button>
      ) : (
        <button type="button" className="app-button" onClick={copy}>
          <Icon name={copied ? "check" : "copy"} size={12} />
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </span>
  );
}

const STEP_NAMES: Record<NumberPath["steps"][number]["step"], string> = { carrier: "Carrier", fence: "Admission", world: "Environment", agent: "Agent" };

/** What a call to the number goes through now, step by step, each with what would fix it. */
export function Path({ number, round = 0 }: { number: string; round?: number }): ReactNode {
  const credentials = useCredentials();
  const [path, setPath] = useState<NumberPath | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    let gone = false;
    readPath(credentials, number).then((read) => !gone && setPath(read), (failed: unknown) => !gone && setRefused(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials, number, round]);
  if (refused !== null) return <p className="cfg-refused">{refused}</p>;
  if (path === null) return <p className="dash-quiet">Reading its path…</p>;
  return (
    <ol className="num-path">
      {path.steps.map((step) => (
        <li key={step.step} className={`num-path-step num-path-${step.state}`}>
          <span className="num-path-dot" aria-hidden="true" />
          <span className="num-path-words">
            <span className="num-path-name">{STEP_NAMES[step.step]}</span>
            <span className="num-path-says">{step.says}</span>
            {step.fix != null && step.fix !== "" && <span className="num-path-fix">{step.fix}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
