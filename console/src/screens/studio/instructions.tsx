/** The editor's first two tabs: what the agent is told, and how it opens a call. */

import { useRef, type ReactNode } from "react";

import { Input, Segmented } from "../../ui";
import type { Greeting } from "./door";
import { greetingOf, greetingText, openingOf, PLACEHOLDERS, type Opening } from "./draft";
import { Section } from "./section";

const OPENINGS: readonly { value: Opening; label: string }[] = [
  { value: "none", label: "The caller speaks first" },
  { value: "say", label: "Say these words" },
  { value: "reply", label: "Let the model open" },
];

// What the instructions may name, in a person's words, each inserted where the cursor is.
const INSERTS: Readonly<Record<string, string>> = {
  "{{call.today}}": "Today",
  "{{call.from}}": "Caller's number",
  "{{call.to}}": "Number called",
  "{{call.channel}}": "Channel",
  "{{caller.name}}": "Caller's name",
  "{{metadata.KEY}}": "Metadata",
};

const wordsIn = (text: string): number => (text.trim() === "" ? 0 : text.trim().split(/\s+/).length);

export function Instructions({ text, onChange, tip }: { text: string; onChange: (text: string) => void; tip: ReactNode }): ReactNode {
  const area = useRef<HTMLTextAreaElement>(null);

  // A name goes where the cursor is, in place of what is selected, and the cursor stays after it.
  const insert = (name: string): void => {
    const box = area.current;
    const from = box?.selectionStart ?? text.length;
    const to = box?.selectionEnd ?? text.length;
    onChange(`${text.slice(0, from)}${name}${text.slice(to)}`);
    window.requestAnimationFrame(() => {
      box?.focus();
      box?.setSelectionRange(from + name.length, from + name.length);
    });
  };

  return (
    <div className="sto-panel">
      <p className="sto-blurb">What the agent is, what it knows, and how it behaves. Write it like you&apos;d brief a new colleague.</p>
      <div className="sto-editor">
        <textarea ref={area} className="sto-instructions" rows={13} spellCheck={false} aria-label="Instructions" value={text} onChange={(event) => onChange(event.target.value)} />
        <div className="sto-insert">
          <span className="sto-insert-label">Insert</span>
          {PLACEHOLDERS.map((name) => (
            <button key={name} type="button" className="sto-insert-one" title={name} onClick={() => insert(name)}>
              {INSERTS[name] ?? name}
            </button>
          ))}
          <span className="sto-insert-count">{wordsIn(text)} words</span>
        </div>
      </div>
      {tip}
    </div>
  );
}

export function GreetingSection({ greeting, onChange }: { greeting: Greeting | null | undefined; onChange: (greeting: Greeting | null) => void }): ReactNode {
  const opening = openingOf(greeting);
  const text = greetingText(greeting);
  return (
    <Section title="Greeting" meta="what happens when the call is answered">
      <Segmented options={OPENINGS} value={opening} onChange={(chosen) => onChange(greetingOf(chosen, text))} />
      {opening !== "none" && (
        <Input
          value={text}
          aria-label={opening === "say" ? "The words said" : "The instruction the model opens with"}
          placeholder={opening === "say" ? "Hello, thanks for calling. How can I help?" : "Greet the caller by name if you know it, and ask how you can help."}
          onChange={(event) => onChange(greetingOf(opening, event.target.value))}
        />
      )}
      <p className="sto-hint">
        {opening === "none" && "The agent waits for the caller to say something."}
        {opening === "say" && "These exact words are said the moment the call is answered."}
        {opening === "reply" && "The model reads this instruction and opens the call in its own words."}
      </p>
    </Section>
  );
}
