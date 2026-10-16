/** Memory and Knowledge sections of the settings form. */

import type { ReactNode } from "react";

import { Label, TextArea } from "../../ui";
import type { Change, Typed } from "./typed";

export function MemorySection({ typed, change }: { typed: Typed; change: Change }): ReactNode {
  return (
    <section className="set-section">
      <div className="set-section-head">
        <h2 className="set-section-title">Memory</h2>
        <p className="set-section-blurb">What the agent writes down about a caller when the call ends, and hands back the next time that number calls.</p>
      </div>
      <div className="set-row">
        <div className="set-field">
          <Label>Remember</Label>
          <TextArea value={typed.remember} rows={5} aria-label="Remember" placeholder={"their name and phone\nallergies\nthe morning or the afternoon they prefer"} onChange={(event) => change("remember", event.target.value)} />
          <p className="set-help">One kind of fact per line, in your words. The extraction keeps only these.</p>
        </div>
        <div className="set-field">
          <Label>Never keep</Label>
          <TextArea value={typed.forget} rows={5} aria-label="Never keep" placeholder={"card numbers\nanything about payment"} onChange={(event) => change("forget", event.target.value)} />
          <p className="set-help">One per line. What is named here is never written down, whatever a caller says.</p>
        </div>
      </div>
    </section>
  );
}

export function KnowledgeSection({ typed, change }: { typed: Typed; change: Change }): ReactNode {
  return (
    <section className="set-section">
      <div className="set-section-head">
        <h2 className="set-section-title">Knowledge</h2>
        <p className="set-section-blurb">What the agent knows by heart: the business as you would tell a new receptionist. Read whole on every call, so keep it to what every call may need.</p>
      </div>
      <div className="set-field set-wide">
        <Label>By heart, in Markdown</Label>
        <TextArea
          value={typed.knowledge}
          aria-label="By heart, in Markdown"
          rows={16}
          spellCheck={false}
          placeholder={"# Clínica Norte\n\n## Hours\nMonday to Friday, 9:00 to 20:00.\n\n## Prices\nA first visit is 60 euros.\n\n## Needs an authorisation\nAn X-ray, an extraction, anything over 300 euros."}
          onChange={(event) => change("knowledge", event.target.value)}
        />
        <p className="set-help">{typed.knowledge.length.toLocaleString("en-US")} characters. The documents it searches are not this: those are the Docs tab, attached under Bases.</p>
      </div>
    </section>
  );
}
