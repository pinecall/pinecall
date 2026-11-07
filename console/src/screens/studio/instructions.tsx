/** The editor's first tab: what the agent is told, with the call's own values inserted where the cursor is. */

import { useLayoutEffect, useRef, type ReactNode } from "react";

import { PLACEHOLDERS } from "./draft";

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

export function Instructions({ text, onChange }: { text: string; onChange: (text: string) => void }): ReactNode {
  const area = useRef<HTMLTextAreaElement>(null);

  // The box grows with the text; the stylesheet's floor and ceiling bound it.
  useLayoutEffect(() => {
    const box = area.current;
    if (box === null) return;
    box.style.height = "auto";
    box.style.height = `${String(box.scrollHeight)}px`;
  }, [text]);

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
        <textarea ref={area} className="sto-instructions" rows={8} spellCheck={false} aria-label="Instructions" value={text} onChange={(event) => onChange(event.target.value)} />
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
    </div>
  );
}
