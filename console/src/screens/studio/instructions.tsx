/** The editor's first two sections: what the agent is told, and how it opens a call. */

import type { ReactNode } from "react";

import { Input, Segmented, TextArea } from "../../ui";
import type { Greeting } from "./door";
import { greetingOf, greetingText, openingOf, PLACEHOLDERS, type Opening } from "./draft";
import { Section } from "./section";

const OPENINGS: readonly { value: Opening; label: string }[] = [
  { value: "none", label: "The caller speaks first" },
  { value: "say", label: "Say these words" },
  { value: "reply", label: "Let the model open" },
];

export function Instructions({ text, onChange }: { text: string; onChange: (text: string) => void }): ReactNode {
  return (
    <Section title="Instructions" meta="what the agent is, what it knows, how it behaves">
      <TextArea className="ui-textarea sto-instructions" value={text} rows={12} aria-label="Instructions" onChange={(event) => onChange(event.target.value)} />
      <p className="sto-hint">
        Filled in when a call starts: {PLACEHOLDERS.map((one, at) => (
          <span key={one}>
            <span className="ui-fixed">{one}</span>
            {at < PLACEHOLDERS.length - 1 ? ", " : "."}
          </span>
        ))}
      </p>
    </Section>
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
