/** Whether the model may end the call itself, and on what: never, when it judges the call over, or only on a condition said in words. */

import { useState, type ReactNode } from "react";

import { Select, type SelectItem } from "../ui/select";
import { Field } from "../ui/setting";
import { EditDialog } from "./dialog";
import type { TuningBody } from "./door";

type Hangup = NonNullable<TuningBody["hangup"]>;
type Mode = "never" | "any" | "when";

const MODES: readonly SelectItem[] = [
  { value: "never", label: "Never", detail: "The agent has no way to end the call: the caller hangs up." },
  { value: "any", label: "When it judges the call is over", detail: "The model decides, says its goodbye and ends the call." },
  { value: "when", label: "Only when…", detail: "The model may end the call on a condition you write." },
];

/** What a row says of it: the mode in a few words. */
export function hangupSaid(hangup: Hangup | null): string {
  if (hangup === null) return "Never";
  return hangup.when == null || hangup.when === "" ? "When it judges the call is over" : `When ${hangup.when}`;
}

export function HangupEditor({ initial, saving, refused, onClose, onSave }: { initial: Hangup | null; saving: boolean; refused: string | null; onClose: () => void; onSave: (hangup: Hangup | null) => Promise<boolean> }): ReactNode {
  const when = initial?.when ?? "";
  const [mode, setMode] = useState<Mode>(initial === null ? "never" : when === "" ? "any" : "when");
  const [text, setText] = useState(when);
  const save = (): void => void onSave(mode === "never" ? null : { when: mode === "when" ? text.trim() : "" });
  return (
    <EditDialog title="Hang up" icon="leave" about="Whether the agent may end the call itself." saving={saving} refused={refused} onClose={onClose} onSave={save}>
      <Field label="May the agent end the call?">
        <Select items={MODES} value={mode} label="May the agent end the call?" searchable={false} onChange={(picked) => setMode(picked as Mode)} />
      </Field>
      {mode === "when" && (
        <label className="cfg-field">
          It may hang up when…
          <input className="cfg-input" value={text} autoFocus placeholder="the caller has their appointment and said goodbye" onChange={(event) => setText(event.target.value)} />
          <span className="dash-quiet">The model reads this sentence as the rule for ending the call.</span>
        </label>
      )}
      {mode !== "never" && (
        <dl className="cfg-reach">
          <dt>How it ends a call</dt>
          <dd>
            <b>Goodbye first.</b> It says its goodbye in the same answer, then the line closes for the caller.
          </dd>
          <dd>
            <b>Not while greeting.</b> It cannot hang up before the caller has had a turn.
          </dd>
        </dl>
      )}
    </EditDialog>
  );
}
