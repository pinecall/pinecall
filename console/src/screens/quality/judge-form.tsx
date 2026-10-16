/** The form one of the org's or an agent's own judges is written in: a name, the question, how it answers, when it runs, what it reads — tried before it is kept. */

import { useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { JudgeAnswer, JudgeOn, JudgeRead } from "@pinecall/core/wire/rest-evals";
import { Button, Check, Field, Input, Segmented, TextArea } from "../../ui";
import { writeJudge, type JudgeRequest, type JudgeRow, type Whose } from "./judges-door";
import { TryJudge } from "./try-judge";

// The gateway's rule for the name call.score gives the answer (runtime domain/judging.py).
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const READS: readonly { read: JudgeRead; label: string }[] = [
  { read: "prompt", label: "The agent's prompt, as the call ran it" },
  { read: "evidence", label: "The evidence: what the call was shown, its tool answers, its states" },
  { read: "facts", label: "The call's facts: the org, the direction, an opt-out, how it ended" },
];

/** `editing` opens the form on a judge already written; `agent` is the agent whose calls a try is asked of, none at the org's level. */
export function JudgeForm({ whose, agent, editing, onSaved, onClose }: { whose: Whose; agent: string; editing: JudgeRow | null; onSaved: (judges: JudgeRow[]) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState(editing?.name ?? "");
  const [question, setQuestion] = useState(editing?.question ?? "");
  const [answer, setAnswer] = useState<JudgeAnswer>(editing?.answer ?? "verdict");
  const [choices, setChoices] = useState((editing?.choices ?? []).join(", "));
  const [when, setWhen] = useState<JudgeOn>(editing?.when ?? "always");
  const [trigger, setTrigger] = useState(editing?.trigger ?? "");
  const [reads, setReads] = useState<ReadonlySet<JudgeRead>>(new Set(editing?.reads ?? []));
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const listed = choices
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
  const nameOk = A_NAME.test(name);
  const ready = nameOk && question.trim() !== "" && (answer !== "choice" || listed.length >= 2) && (when !== "trigger" || trigger.trim() !== "") && !saving;
  const written: JudgeRequest = {
    question: question.trim(),
    answer,
    choices: answer === "choice" ? listed : [],
    when,
    trigger: when === "trigger" ? trigger.trim() : "",
    reads: READS.map((one) => one.read).filter((read) => reads.has(read)),
  };

  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      onSaved(await writeJudge(credentials, whose, name, written));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setSaving(false);
    }
  };
  const read = (one: JudgeRead) => (checked: boolean) => {
    const next = new Set(reads);
    if (checked) next.add(one);
    else next.delete(one);
    setReads(next);
  };

  return (
    <form
      className="qly-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) void save();
      }}
    >
      <Field label="Name">
        <Input size="sm" placeholder="offers-next-slot" value={name} spellCheck={false} disabled={editing !== null} onChange={(event) => setName(event.target.value.toLowerCase().replace(/\s+/g, "-"))} />
        <p className="qly-hint">Lower-case words joined by hyphens, as call.score names the answer. Pinecall&apos;s judges&apos; names are taken.</p>
        {name !== "" && !nameOk && <p className="qly-bad">Only a–z, 0–9 and single hyphens between words.</p>}
      </Field>
      <Field label="The question">
        <TextArea rows={3} placeholder="The agent offered the next free slot before the caller asked twice." value={question} onChange={(event) => setQuestion(event.target.value)} />
        <p className="qly-hint">
          What the judge model answers about the whole call, both sides&apos; turns and the tool calls between them in front of it. Say what fails it and what does not: it judges the spirit, not the letter.{" "}
          {whose === null ? "Asked of every agent's calls." : `About ${whose}'s job alone.`}
        </p>
      </Field>
      <Field label="It answers">
        <Segmented<JudgeAnswer>
          options={[
            { value: "verdict", label: "held or broke" },
            { value: "choice", label: "one of several" },
            { value: "score", label: "a score, 1 to 5" },
          ]}
          value={answer}
          onChange={setAnswer}
        />
        {answer === "choice" && <Input size="sm" placeholder="calm, upset, angry" value={choices} onChange={(event) => setChoices(event.target.value)} />}
        <p className="qly-hint">Only held or broke judges a call; a choice or a score classifies it.</p>
      </Field>
      <Field label="It runs on">
        <Segmented<JudgeOn>
          options={[
            { value: "always", label: "every call" },
            { value: "simulations", label: "simulated calls" },
            { value: "trigger", label: "a call it applies to" },
          ]}
          value={when}
          onChange={setWhen}
        />
        {when === "trigger" && <TextArea rows={2} placeholder="The caller asked to reschedule." value={trigger} onChange={(event) => setTrigger(event.target.value)} />}
        <p className="qly-hint">A trigger is a short yes-or-no asked first: a no is N/A, and the question is never asked.</p>
      </Field>
      <Field label="It also reads">
        {READS.map((one) => (
          <Check key={one.read} checked={reads.has(one.read)} onChange={read(one.read)}>
            {one.label}
          </Check>
        ))}
      </Field>
      {agent === "" ? <p className="qly-hint">Put an agent in view to try a judge on its calls before you keep it.</p> : <TryJudge agent={agent} name={name} written={written} />}
      <div className="qly-form-foot">
        <Button size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" kind="primary" type="submit" disabled={!ready}>
          {saving ? "Saving…" : "Save"}
        </Button>
        {refused !== null && <span className="qly-bad">{refused}</span>}
      </div>
    </form>
  );
}
