/** The editor's Greeting tab: how the agent picks up — it listens, it says set words, or the model opens — and the words or the instruction. */

import type { ReactNode } from "react";

import { Icon, type IconName } from "../../ui";
import type { Greeting } from "./door";
import { greetingOf, greetingText, openingOf, type Opening } from "./draft";

const OPENINGS: readonly { value: Opening; icon: IconName; title: string; sub: string }[] = [
  { value: "none", icon: "ear", title: "Caller speaks first", sub: "The agent picks up and listens." },
  { value: "say", icon: "speaker", title: "Say a set greeting", sub: "The same words on every call." },
  { value: "reply", icon: "bot", title: "Let the agent greet", sub: "In its own words, from your instruction." },
];

export function GreetingTab({ greeting, onChange }: { greeting: Greeting | null | undefined; onChange: (greeting: Greeting | null) => void }): ReactNode {
  const opening = openingOf(greeting);
  const text = greetingText(greeting);
  return (
    <div className="sto-panel">
      <p className="sto-blurb">How the agent picks up the phone.</p>
      <div className="sto-openings" role="radiogroup" aria-label="How the call opens">
        {OPENINGS.map((one) => (
          <button
            key={one.value}
            type="button"
            role="radio"
            aria-checked={opening === one.value}
            className={opening === one.value ? "sto-opening sto-opening-on" : "sto-opening"}
            onClick={() => onChange(greetingOf(one.value, text))}
          >
            <span className="sto-opening-icon">
              <Icon name={one.icon} size={16} />
            </span>
            <span className="sto-opening-title">{one.title}</span>
            <span className="sto-opening-sub">{one.sub}</span>
          </button>
        ))}
      </div>
      {opening !== "none" && (
        <div className="sto-editor">
          <textarea
            className="sto-greeting"
            rows={3}
            value={text}
            aria-label={opening === "say" ? "The words said" : "The instruction the agent opens with"}
            placeholder={opening === "say" ? "Hello, thanks for calling. How can I help?" : "Greet the caller by name if you know it, and ask how you can help."}
            onChange={(event) => onChange(greetingOf(opening, event.target.value))}
          />
          <div className="sto-insert">
            <span className="sto-insert-label">{opening === "say" ? "Said word for word the moment the call is answered." : "An instruction, not a script: the agent opens in its own words."}</span>
          </div>
        </div>
      )}
    </div>
  );
}
