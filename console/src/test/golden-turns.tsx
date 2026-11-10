/** A golden's turns in its form: each line the caller says, and under it the steps that must follow, in order. */

import type { ReactNode } from "react";

import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { A_STEP, type StepForm, type TurnForm } from "./fold";

const ADDS: readonly { kind: StepForm["kind"]; name: string }[] = [
  { kind: "tool", name: "calls a tool" },
  { kind: "reply", name: "replies" },
  { kind: "no_tool", name: "does not call" },
  { kind: "end", name: "the call ends" },
  { kind: "nothing_else", name: "nothing else" },
];

const NAMES: Record<StepForm["kind"], string> = { tool: "Calls the tool", no_tool: "Does not call", reply: "Replies", end: "The call ends", nothing_else: "Does nothing else in this turn" };

const ENDERS = [
  { value: "agent", label: "The agent hangs up" },
  { value: "caller", label: "The caller hangs up" },
];

function StepFields({ step, onChange }: { step: StepForm; onChange: (step: StepForm) => void }): ReactNode {
  switch (step.kind) {
    case "tool":
      return (
        <>
          <input className="cfg-input" aria-label="Tool" placeholder="find_slots" spellCheck={false} value={step.tool} onChange={(event) => onChange({ ...step, tool: event.target.value })} />
          <input className="cfg-input" aria-label="With these arguments" placeholder='With these arguments, optional: {"day": "thursday"}' spellCheck={false} value={step.args} onChange={(event) => onChange({ ...step, args: event.target.value })} />
        </>
      );
    case "no_tool":
      return <input className="cfg-input" aria-label="Tool" placeholder="book" spellCheck={false} value={step.tool} onChange={(event) => onChange({ ...step, tool: event.target.value })} />;
    case "reply":
      return (
        <>
          <input className="cfg-input" aria-label="Says" placeholder="Says these words: 10:15, Thursday" value={step.says} onChange={(event) => onChange({ ...step, says: event.target.value })} />
          <input className="cfg-input" aria-label="Says one of" placeholder="Or any one of these: sorry, apologies" value={step.saysAny} onChange={(event) => onChange({ ...step, saysAny: event.target.value })} />
          <input className="cfg-input" aria-label="Never says" placeholder="Never says: free" value={step.never} onChange={(event) => onChange({ ...step, never: event.target.value })} />
          <input className="cfg-input" aria-label="Means" placeholder="Means, read by a judge: offers a Thursday slot" value={step.intent} onChange={(event) => onChange({ ...step, intent: event.target.value })} />
        </>
      );
    case "end":
      return <Select label="Who ends the call" searchable={false} items={ENDERS.some((one) => one.value === step.by) ? ENDERS : [...ENDERS, { value: step.by, label: `The ${step.by} ends it` }]} value={step.by} onChange={(by) => onChange({ ...step, by: by as typeof step.by })} />;
    case "nothing_else":
      return null;
  }
}

/** The turns, edited in place: a line gains steps one at a time, and the last line is followed by the way to add another. */
export function TurnsEditor({ turns, onChange }: { turns: readonly TurnForm[]; onChange: (turns: TurnForm[]) => void }): ReactNode {
  const set = (at: number, turn: TurnForm): void => onChange(turns.map((one, index) => (index === at ? turn : one)));
  let line = 0;
  return (
    <div className="tst-turns">
      {turns.map((turn, at) => {
        if ("event" in turn) {
          return (
            <div key={at} className="tst-turn tst-turn-event">
              The backend sends <b>{turn.event.event?.name ?? "an event"}</b>
            </div>
          );
        }
        line += 1;
        const setStep = (which: number, step: StepForm): void => set(at, { ...turn, steps: turn.steps.map((one, index) => (index === which ? step : one)) });
        return (
          <div key={at} className="tst-turn">
            <div className="tst-turn-says">
              <span className="tst-turn-number">{line}</span>
              <input className="cfg-input" aria-label={`Line ${line}, the caller says`} placeholder={line === 1 ? "How much is a cleaning?" : "And with insurance?"} value={turn.say} onChange={(event) => set(at, { ...turn, say: event.target.value })} />
              {turns.length > 1 && (
                <button type="button" className="tst-x" aria-label={`Remove line ${line}`} onClick={() => onChange(turns.filter((_, index) => index !== at))}>
                  <Icon name="close" size={13} />
                </button>
              )}
            </div>
            {turn.steps.map((step, which) => (
              <div key={which} className="tst-step">
                <div className="tst-step-top">
                  <span className="tst-step-name">
                    <span className="tst-step-order">then</span>
                    {NAMES[step.kind]}
                  </span>
                  <button type="button" className="tst-x" aria-label="Remove this step" onClick={() => set(at, { ...turn, steps: turn.steps.filter((_, index) => index !== which) })}>
                    <Icon name="close" size={13} />
                  </button>
                </div>
                <StepFields step={step} onChange={(next) => setStep(which, next)} />
              </div>
            ))}
            <div className="tst-adds">
              <span>{turn.steps.length === 0 ? "Then the agent" : "and then"}</span>
              {ADDS.map((add) => (
                <button key={add.kind} type="button" onClick={() => set(at, { ...turn, steps: [...turn.steps, A_STEP[add.kind]] })}>
                  {add.name}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      <button type="button" className="app-button tst-add-line" onClick={() => onChange([...turns, { say: "", steps: [] }])}>
        <Icon name="plus" size={12} />
        Add a line
      </button>
    </div>
  );
}
