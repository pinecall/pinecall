/** New case: a golden a person writes for the agent in view, kept approved, played by the nightly; no call behind it. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Check, Field, Input, Segmented, TextArea } from "../../ui";
import { writeCase, type EvalCase } from "./door";
import { BLANK, goldenOf, type Written } from "./written";

const REGISTERS = [
  { value: "", label: "Either" },
  { value: "tu", label: "tú" },
  { value: "usted", label: "usted" },
] as const;

/**
 * The same case whatever wrote the agent: a class or Studio. `state` and the tools are the
 * class's own names, so a case that names them breaks when the class renames them — that is a
 * golden for the repository (`pinecall cases pull`), and the form says so.
 */
export function NewCase({ agent, onWritten, onClose }: { agent: string; onWritten: (kept: EvalCase) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [form, setForm] = useState<Written>(BLANK);
  const [refused, setRefused] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Written>(field: K) => (value: Written[K]): void => setForm((was) => ({ ...was, [field]: value }));

  const save = async (): Promise<void> => {
    const made = goldenOf(form);
    if ("refused" in made) return setRefused(made.refused);
    setBusy(true);
    try {
      onWritten(await writeCase(credentials, agent, made.golden.name, { golden: made.golden, held_out: form.heldOut }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const namesCode = form.state.trim() !== "" || form.tools.trim() !== "" || form.notTools.trim() !== "";
  return (
    <section className="cs-new">
      <h2 className="cs-new-title">New case for {agent}</h2>
      <Field label="Name">
        <Input value={form.name} placeholder="no-dice-un-precio" onChange={(event) => set("name")(event.target.value)} />
      </Field>
      <Field label="What the caller says, one line each">
        <TextArea rows={3} value={form.lines} placeholder="¿Cuánto cuesta una resonancia?" onChange={(event) => set("lines")(event.target.value)} />
      </Field>
      <Field label="The state it opens in (JSON, optional)">
        <TextArea rows={2} value={form.state} placeholder='{"stage": "choose"}' onChange={(event) => set("state")(event.target.value)} />
      </Field>
      <div className="ui-form">
        <Field label="Says, comma-separated" grow>
          <Input value={form.says} onChange={(event) => set("says")(event.target.value)} />
        </Field>
        <Field label="Never says" grow>
          <Input value={form.not} placeholder="euros, €" onChange={(event) => set("not")(event.target.value)} />
        </Field>
      </div>
      <div className="ui-form">
        <Field label="Calls these tools" grow>
          <Input value={form.tools} placeholder="book" onChange={(event) => set("tools")(event.target.value)} />
        </Field>
        <Field label="Never calls" grow>
          <Input value={form.notTools} onChange={(event) => set("notTools")(event.target.value)} />
        </Field>
      </div>
      <div className="ui-form">
        <Field label="Register">
          <Segmented options={REGISTERS} value={form.register} onChange={set("register")} />
        </Field>
        <Check checked={form.grounded} onChange={set("grounded")}>
          Grounded in its documents
        </Check>
        <Check checked={form.heldOut} onChange={set("heldOut")}>
          Held out of the nightly
        </Check>
      </div>
      {namesCode && (
        <p className="cs-none">
          This case names the agent&apos;s state or tools. If the agent is a class, keep it beside the code: <span className="ui-fixed">pinecall cases pull {form.name.trim() || "<name>"}</span>.
        </p>
      )}
      {refused !== null && <p className="cs-bad">{refused}</p>}
      <div className="cs-new-actions">
        <Button kind="primary" disabled={busy} onClick={() => void save()}>
          {busy ? "Saving…" : "Save case"}
        </Button>
        <Button disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
