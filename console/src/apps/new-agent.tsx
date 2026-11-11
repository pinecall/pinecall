/** New agent, in the side panel, in three steps: who it is and what it does, how it sounds, and a way to reach it — here, from a mobile, or at a number of its own. */

import { useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readReport, type Report } from "../configure/door";
import { VoicePicker } from "../configure/stage-editor";
import { AddNumberPanel } from "../numbers/add-number";
import { TestLine } from "../numbers/test-line";
import { Icon, type IconName } from "../shell/icons";
import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { removeApp } from "./door";
import { makeStudioAgent, setSound } from "./studio-door";
import "../numbers/numbers.css";

const A_NAME = /^[a-z][a-z0-9-]*$/;
// How often, and how many times, a new agent's pipeline is asked for while the gateway brings it up: fifteen seconds, where one is usual.
const ASKED_AGAIN_MS = 1500;
const ASKED_AT_MOST = 10;
const LONGEST = 40;

const SPOKEN = "Everything you say is read aloud: keep it short, one question at a time, no lists and no symbols.";

/** What an agent starts as: its instructions and how it opens the call, both rewritten later in Configure. */
const STARTS: readonly { value: string; label: string; detail: string; instructions: string; greeting: string }[] = [
  { value: "front-desk", label: "Front desk", detail: "Answers, helps, takes a message", instructions: `You answer the phone for the business. Find out what the caller needs and help with what you know. When you cannot help, take their name, their number and a short message, and say somebody will call back. ${SPOKEN}`, greeting: "Hello, thanks for calling. How can I help?" },
  { value: "appointments", label: "Appointments", detail: "Books, moves and cancels", instructions: `You book appointments for the business. Ask what the appointment is for, then the day and time they prefer, then their name and number. Read the appointment back before you confirm it. For a change or a cancellation, ask for the name it is under first. ${SPOKEN}`, greeting: "Hello, thanks for calling. Would you like to book an appointment?" },
  { value: "support", label: "Support", detail: "Solves a problem, or hands it on", instructions: `You are the first line of support. Ask what is wrong, and for the account or order it is about. Solve it when you know how. When you do not, say so plainly, take their contact, and say the team will follow up. Never guess a fix. ${SPOKEN}`, greeting: "Hi, this is support. What can I help you with?" },
  { value: "leads", label: "Sales", detail: "Qualifies a caller and takes their details", instructions: `You talk to people interested in the business. Find out what they are looking for, how soon, and for how many people. Answer what you know, never invent a price, and take their name, company and the best way to reach them. ${SPOKEN}`, greeting: "Hi, thanks for your interest. What are you looking for?" },
  { value: "blank", label: "Start from nothing", detail: "You write every word", instructions: "", greeting: "" },
];

// The zone proposed for a new agent is this browser's: whoever makes it is most often where its callers are.
const HERE = Intl.DateTimeFormat().resolvedOptions().timeZone;
const ZONES = [{ value: "", label: "None", detail: "The agent is told the day only, and no hour" }, ...Intl.supportedValuesOf("timeZone").map((zone) => ({ value: zone, label: zone }))];

const LANGUAGES = [
  { value: "", label: "Whichever the caller speaks", detail: "Nothing is pinned" },
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "pt", label: "Portuguese" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "it", label: "Italian" },
];

function nameRefused(name: string, taken: ReadonlySet<string>): string | null {
  if (!A_NAME.test(name)) return "A name is lowercase letters, digits and dashes, starting with a letter: front-desk.";
  if (name.length > LONGEST) return `A name is at most ${LONGEST} characters.`;
  return taken.has(name) ? `There is already an agent called ${name}.` : null;
}

function Way({ icon, name, says, onClick }: { icon: IconName; name: string; says: string; onClick: () => void }): ReactNode {
  return (
    <button type="button" className="num-way" onClick={onClick}>
      <span className="num-way-mark">
        <Icon name={icon} size={17} />
      </span>
      <span className="num-way-words">
        <span className="num-way-name">{name}</span>
        <span className="num-way-says">{says}</span>
      </span>
      <Icon name="chevron" size={15} />
    </button>
  );
}

/** `onMade` as soon as the gateway holds it, so the list has it; `onOpen` when the person leaves the panel for the agent, to talk to it or not. */
export function NewAgentPanel({ taken, onMade, onOpen, onClose }: { taken: ReadonlySet<string>; onMade: (name: string) => void; onOpen: (name: string, talk: boolean) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState("");
  const [start, setStart] = useState(STARTS[0]?.value ?? "blank");
  const [instructions, setInstructions] = useState(STARTS[0]?.instructions ?? "");
  const [greeting, setGreeting] = useState(STARTS[0]?.greeting ?? "");
  const [language, setLanguage] = useState("");
  const [voice, setVoice] = useState("");
  const [timezone, setTimezone] = useState(HERE);
  // What the new agent speaks with, read once it is made: the voices offered are that vendor's.
  const [speaks, setSpeaks] = useState<{ vendor: string; model: string } | null>(null);
  const [sounded, setSounded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);
  const [reach, setReach] = useState<"mobile" | "number" | null>(null);

  const pick = (value: string): void => {
    const picked = STARTS.find((one) => one.value === value);
    if (picked === undefined) return;
    setStart(value);
    setInstructions(picked.instructions);
    setGreeting(picked.greeting);
  };

  // The new agent's pipeline, asked until the gateway holds it; null when it never does.
  const answering = async (called: string): Promise<Report | null> => {
    for (let left = ASKED_AT_MOST; left > 0; left -= 1) {
      try {
        return await readReport(credentials, called);
      } catch {
        await new Promise((done) => window.setTimeout(done, ASKED_AGAIN_MS));
      }
    }
    return null;
  };

  const make = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const called = name.trim();
    const wrong = nameRefused(called, taken) ?? (instructions.trim() === "" ? "Write what it does: its instructions are what it is." : null);
    if (wrong !== null) return setRefused(wrong);
    setBusy(true);
    setRefused(null);
    try {
      await makeStudioAgent(credentials, called, { instructions: instructions.trim(), greeting: greeting.trim() === "" ? null : { say: greeting.trim() }, tools: [], collect: null });
      // Made is not answering: the gateway keeps an agent it cannot start, as it does one whose name another organization already uses, so the wizard waits to see it up before going on.
      const report = await answering(called);
      if (report === null) {
        const removed = await removeApp(credentials, called).then(() => true, () => false);
        onMade(called);
        return setRefused(`${called} was made but the gateway could not start it. The usual reason is its name: a name belongs to one organization across all of Pinecall, and another already uses this one. ${removed ? "It was removed: choose another name." : "Remove it from the list, then choose another name."}`);
      }
      setSpeaks({ vendor: report.speaks.vendor, model: report.speaks.model ?? "" });
      setMade(called);
      onMade(called);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  // Nothing chosen is nothing to keep: the agent runs on each vendor's own.
  const keepSound = async (): Promise<void> => {
    if (made === null) return;
    if (language === "" && voice === "" && timezone === "") return setSounded(true);
    setBusy(true);
    setRefused(null);
    try {
      await setSound(credentials, made, { language, voice, timezone });
      setSounded(true);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  if (made !== null && !sounded) {
    return (
      <SidePanel
        title="How it sounds"
        icon="speaker"
        about={`${made} is made. Pick the language it is pinned to, the voice it speaks in and the time zone its clock is read in, or skip and change them in Configure.`}
        onClose={() => onOpen(made, false)}
        footer={
          <>
            {refused !== null && (
              <p className="cfg-refused" role="alert">
                {refused}
              </p>
            )}
            <div className="cfg-dialog-foot">
              <button type="button" className="app-button" disabled={busy} onClick={() => setSounded(true)}>
                Skip
              </button>
              <button type="button" className="cfg-save" disabled={busy} onClick={() => void keepSound()}>
                {busy ? "Saving…" : "Continue"}
              </button>
            </div>
          </>
        }
      >
        <Field label="Language">
          <Select label="Language" searchable={false} items={LANGUAGES} value={language} onChange={(picked) => (setLanguage(picked), setVoice(""))} />
        </Field>
        <Field label="Voice">{speaks === null ? <p className="dash-quiet">Reading its voices…</p> : <VoicePicker key={language} vendor={speaks.vendor} model={speaks.model} language={language === "" ? null : language} voice={voice} onVoice={setVoice} />}</Field>
        <Field label="Time zone">
          <Select label="Time zone" items={ZONES} value={timezone} onChange={setTimezone} />
        </Field>
      </SidePanel>
    );
  }

  if (made !== null && reach === "number") return <AddNumberPanel agents={[made]} agent={made} onAdded={() => undefined} onClose={() => setReach(null)} />;

  if (made !== null) {
    return (
      <SidePanel
        title={`${made} is ready`}
        icon="agents"
        about="It answers in the sandbox from now on. Reach it one of these ways, or open it and keep building."
        onClose={() => onOpen(made, false)}
        footer={
          <div className="cfg-dialog-foot">
            <button type="button" className="cfg-save" onClick={() => onOpen(made, false)}>
              Open {made}
            </button>
          </div>
        }
      >
        <div className="num-ways">
          <Way icon="chat" name="Talk to it here" says="A chat or a voice call from this page, with your microphone." onClick={() => onOpen(made, true)} />
          <Way icon="numbers" name="Call it from your mobile" says="Say which mobile is yours and call Pinecall's test number. No number of your own needed." onClick={() => setReach(reach === "mobile" ? null : "mobile")} />
          {reach === "mobile" && <TestLine agents={[made]} agent={made} />}
          <Way icon="plus" name="Give it a number" says="Buy one, bring one from Twilio or your carrier, or connect WhatsApp." onClick={() => setReach("number")} />
        </div>
      </SidePanel>
    );
  }

  return (
    <SidePanel
      title="New agent"
      icon="agents"
      about="Built here, with no code. It answers in the sandbox the moment it is made, and reaches production when you deploy it."
      onClose={onClose}
      footer={
        <>
          {refused !== null && (
            <p className="cfg-refused" role="alert">
              {refused}
            </p>
          )}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" disabled={busy} onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form="new-agent" className="cfg-save" disabled={busy || name.trim() === ""}>
              {busy ? "Making it, and waiting for it to answer…" : "Create agent"}
            </button>
          </div>
        </>
      }
    >
      <form id="new-agent" className="cfg-dialog-body" onSubmit={(event) => void make(event)}>
        <Field label="Name">
          <input className="cfg-input" aria-label="Name" placeholder="front-desk" autoFocus spellCheck={false} autoComplete="off" maxLength={LONGEST} value={name} onChange={(event) => (setName(event.target.value.toLowerCase()), setRefused(null))} />
          <span className="num-hint">Lowercase letters, digits and dashes. It is how the agent is named everywhere, and it does not change.</span>
        </Field>
        <Field label="What it does">
          <Select label="What it does" searchable={false} items={STARTS.map((one) => ({ value: one.value, label: one.label, detail: one.detail }))} value={start} onChange={pick} />
        </Field>
        <Field label="Instructions">
          <textarea className="cfg-input cfg-area new-agent-area" aria-label="Instructions" rows={8} placeholder="Who it is, what it helps with, and what it must never do." value={instructions} onChange={(event) => setInstructions(event.target.value)} />
        </Field>
        <Field label="How it opens the call">
          <input className="cfg-input" aria-label="How it opens the call" placeholder="Left empty, the caller speaks first" value={greeting} onChange={(event) => setGreeting(event.target.value)} />
        </Field>
      </form>
    </SidePanel>
  );
}
