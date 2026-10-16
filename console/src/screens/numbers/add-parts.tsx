/** The pieces the ways of Add a number share: the plan read before a write, the agent, the setup to copy, the first call. */

import { useState, type ReactNode } from "react";

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { prettyNumber } from "@pinecall/core/calls";
import { Button, Dot, Input, Label, Select, SelectItem } from "../../ui";
import { readPath, type Wired } from "./door";

/** The gateway's own steps, one per line, in its words — the first token is what kind of thing each is. */
export function Steps({ steps }: { steps: string[] }): ReactNode {
  return (
    <ol className="num-steps">
      {steps.map((step, index) => {
        const [kind, ...rest] = step.split(/\s+/);
        return (
          <li key={index}>
            <span className="num-step-kind">{kind}</span>
            <span className="num-step-text">{rest.join(" ")}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function Planned({ plan, busy, confirm, onConfirm, onCancel }: { plan: Wired; busy: boolean; confirm: string; onConfirm: () => void; onCancel: () => void }): ReactNode {
  return (
    <div className="num-plan">
      <div className="num-plan-title">What will happen. Nothing is changed until you confirm, and nothing is deleted.</div>
      <Steps steps={plan.steps} />
      <div className="num-plan-moves">
        <Button kind="primary" size="md" onClick={onConfirm} disabled={busy}>{busy ? "Working…" : confirm}</Button>
        <Button size="md" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </div>
  );
}

export function AgentPick({ agents, agent, onAgent }: { agents: HeldAgent[]; agent: string; onAgent: (agent: string) => void }): ReactNode {
  return (
    <div className="num-fields num-fields-flush">
      <div>
        <Label>Agent that picks up</Label>
        {agents.length > 0 ? (
          <Select value={agent} onValueChange={onAgent} required>
            {agents.map((held) => (
              <SelectItem key={held.slug} value={held.slug}>{held.slug}</SelectItem>
            ))}
          </Select>
        ) : (
          <Input value={agent} onChange={(e) => onAgent(e.target.value)} placeholder="the agent's slug" required autoComplete="off" />
        )}
      </div>
    </div>
  );
}

export function Setup({ title, meta, children }: { title: string; meta: string; children: ReactNode }): ReactNode {
  return (
    <div className="num-setup">
      <div className="num-setup-head">
        <span className="num-setup-title">{title}</span>
        <span className="num-setup-meta">{meta}</span>
      </div>
      <dl className="num-setup-list">{children}</dl>
    </div>
  );
}

export function Copy({ text }: { text: string }): ReactNode {
  const [copied, setCopied] = useState(false);
  return (
    <span className="num-copy">
      <code>{text}</code>
      <Button size="xs" type="button" onClick={() => void navigator.clipboard.writeText(text).then(() => setCopied(true), () => undefined)}>
        {copied ? "Copied" : "Copy"}
      </Button>
    </span>
  );
}

/** A guided number's last step: its path read when a call starts, until one reaches the box. */
export function FirstCall({ number, onReached }: { number: string; onReached: () => void }): ReactNode {
  const [reached, setReached] = useState(false);
  return (
    <>
      {!reached && <LookForTheFirstCall number={number} onReached={() => setReached(true)} />}
      <FirstCallSaid number={number} reached={reached} onReached={onReached} />
    </>
  );
}

// Mounted only while no call has reached the box: a call to this number starting is when the path changed.
function LookForTheFirstCall({ number, onReached }: { number: string; onReached: () => void }): ReactNode {
  const credentials = useCredentials();
  useFed(
    () => void readPath(credentials, number).then((path) => path.last_call_at != null && onReached(), () => undefined),
    { types: ["call.started"], when: (entry) => entry.data["to"] === number },
    [number],
  );
  return null;
}

function FirstCallSaid({ number, reached, onReached }: { number: string; reached: boolean; onReached: () => void }): ReactNode {
  return (
    <div className="num-waiting">
      <Dot tone={reached ? "green" : "amber"} />
      <span>
        <span className="num-waiting-title">{reached ? "A call reached the box" : "Waiting for the first call"}</span>
        <span className="num-waiting-say">{reached ? "The number rings the agent." : `Call ${prettyNumber(number)} from any phone once the portal is set. This turns green the moment the call reaches the box.`}</span>
      </span>
      {reached && <Button kind="primary" size="sm" onClick={onReached}>Done</Button>}
    </div>
  );
}
