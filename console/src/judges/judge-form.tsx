/** The form a judge of one's own is written in: its name, the one question, how it answers, when it runs and what it reads, tried before it is kept. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { EditDialog } from "../configure/dialog";
import { Field, Toggle } from "../ui/setting";
import { writeJudge, type JudgeAnswer, type JudgeOn, type JudgeRead, type JudgeRequest, type JudgeRow } from "./door";
import { isAName } from "./fold";
import { TryJudge } from "./try";

const ANSWERS: readonly { value: JudgeAnswer; name: string }[] = [
  { value: "verdict", name: "Held or broke" },
  { value: "choice", name: "One of several" },
  { value: "score", name: "A score, 1 to 5" },
];

const WHENS: readonly { value: JudgeOn; name: string }[] = [
  { value: "always", name: "Every call" },
  { value: "simulations", name: "Simulated calls" },
  { value: "trigger", name: "Calls it applies to" },
];

const READS: readonly { read: JudgeRead; title: string; about: string }[] = [
  { read: "prompt", title: "The agent's prompt", about: "As the call ran it." },
  { read: "evidence", title: "The evidence", about: "What the call was shown: its documents, its tool answers, its states." },
  { read: "facts", title: "The call's facts", about: "The direction, an opt-out, how it ended." },
];

function Pick<Value extends string>({ label, options, value, onChange }: { label: string; options: readonly { value: Value; name: string }[]; value: Value; onChange: (value: Value) => void }): ReactNode {
  return (
    <div className="dash-switch jd-pick" role="group" aria-label={label}>
      {options.map((one) => (
        <button key={one.value} type="button" aria-pressed={one.value === value} className={one.value === value ? "dash-switch-on" : ""} onClick={() => onChange(one.value)}>
          {one.name}
        </button>
      ))}
    </div>
  );
}

/** `was` opens the form on a judge already written, whose name is its address and stays. */
export function JudgeForm({ agent, was, onSaved, onClose }: { agent: string; was: JudgeRow | null; onSaved: (judges: JudgeRow[], name: string) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState(was?.name ?? "");
  const [question, setQuestion] = useState(was?.question ?? "");
  const [answer, setAnswer] = useState<JudgeAnswer>(was?.answer ?? "verdict");
  const [choices, setChoices] = useState((was?.choices ?? []).join(", "));
  const [when, setWhen] = useState<JudgeOn>(was?.when ?? "always");
  const [trigger, setTrigger] = useState(was?.trigger ?? "");
  const [reads, setReads] = useState<ReadonlySet<JudgeRead>>(new Set(was?.reads ?? []));
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const listed = choices
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
  const missing = !isAName(name)
    ? "Name it in lower-case words joined by hyphens: offers-next-slot."
    : question.trim() === ""
      ? "Write the question it answers."
      : answer === "choice" && listed.length < 2
        ? "Give it at least two choices, separated by commas."
        : when === "trigger" && trigger.trim() === ""
          ? "Say which calls it applies to."
          : null;
  const written: JudgeRequest = {
    question: question.trim(),
    answer,
    choices: answer === "choice" ? listed : [],
    when,
    trigger: when === "trigger" ? trigger.trim() : "",
    reads: READS.map((one) => one.read).filter((read) => reads.has(read)),
  };

  const save = async (): Promise<void> => {
    if (missing !== null) return setRefused(missing);
    setSaving(true);
    setRefused(null);
    try {
      onSaved(await writeJudge(credentials, agent, name, written), name);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EditDialog
      title={was === null ? "New judge" : `Edit ${was.name}`}
      icon="judges"
      about={agent === "" ? "One question, asked of every agent's calls at hang-up. A judge that breaks opens a case." : `One question about ${agent}'s job, asked of its calls at hang-up. A judge that breaks opens a case.`}
      saving={saving}
      refused={refused}
      onSave={() => void save()}
      onClose={onClose}
    >
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="offers-next-slot" spellCheck={false} disabled={was !== null} value={name} onChange={(event) => setName(event.target.value.toLowerCase().replace(/\s+/g, "-"))} />
      </Field>
      <Field label="The question">
        <textarea className="cfg-input cfg-area" aria-label="The question" rows={4} placeholder="The agent offered the next free slot before the caller asked twice." value={question} onChange={(event) => setQuestion(event.target.value)} />
        <span className="dash-quiet">The judge reads the whole call, both sides and the tool calls between them. Say what fails it and what does not: it judges the spirit, not the letter.</span>
      </Field>
      <Field label="It answers">
        <Pick label="It answers" options={ANSWERS} value={answer} onChange={setAnswer} />
        {answer === "choice" && <input className="cfg-input" aria-label="The choices" placeholder="calm, upset, angry" value={choices} onChange={(event) => setChoices(event.target.value)} />}
        <span className="dash-quiet">{answer === "verdict" ? "Held or broke judges the call: a break opens a case." : "A choice or a score classifies the call. It never breaks it."}</span>
      </Field>
      <Field label="It runs on">
        <Pick label="It runs on" options={WHENS} value={when} onChange={setWhen} />
        {when === "trigger" && <textarea className="cfg-input cfg-area" aria-label="The calls it applies to" rows={2} placeholder="The caller asked to reschedule." value={trigger} onChange={(event) => setTrigger(event.target.value)} />}
        {when === "trigger" && <span className="dash-quiet">A short yes or no asked first. On a no the answer is N/A, the question is never asked, and nothing is billed.</span>}
      </Field>
      <Field label="It also reads">
        <div className="jd-reads">
          {READS.map((one) => (
            <div key={one.read} className="jd-read">
              <span className="jd-read-words">
                <span>{one.title}</span>
                <span className="dash-quiet">{one.about}</span>
              </span>
              <Toggle
                on={reads.has(one.read)}
                label={one.title}
                onChange={(on) => {
                  const next = new Set(reads);
                  if (on) next.add(one.read);
                  else next.delete(one.read);
                  setReads(next);
                }}
              />
            </div>
          ))}
        </div>
      </Field>
      <Field label="Try it before you keep it">
        <TryJudge agent={agent} name={name} written={written} ready={missing === null} />
      </Field>
    </EditDialog>
  );
}
