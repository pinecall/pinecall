/** A terminal panel: each command on a `$` line with what it does over it, copied one at a time or all at once. */

import { useState, type ReactNode } from "react";

export interface Line {
  say: string;
  run: string;
}

function copy(text: string, then: (ok: boolean) => void): void {
  navigator.clipboard.writeText(text).then(
    () => then(true),
    () => then(false),
  );
}

export function Terminal({ lines }: { lines: Line[] }): ReactNode {
  const [copied, setCopied] = useState<number | "all" | null>(null);
  return (
    <div className="wel-panel">
      <div className="wel-panel-head">
        <span className="wel-panel-dots" aria-hidden>
          <i /><i /><i />
        </span>
        <span>Terminal</span>
        <button type="button" className="wel-panel-copy" onClick={() => copy(lines.map((line) => line.run).join("\n"), (ok) => setCopied(ok ? "all" : null))}>
          {copied === "all" ? "Copied" : "Copy all"}
        </button>
      </div>
      <pre className="wel-panel-body">
        {lines.map((line, index) => (
          <span key={line.run} className="wel-term-line">
            <span className="wel-tok-comment"># {line.say}</span>
            {"\n"}
            <span className="wel-term-prompt">$ </span>
            {line.run}
            <button type="button" className="wel-term-copy" aria-label="Copy" onClick={() => copy(line.run, (ok) => setCopied(ok ? index : null))}>
              {copied === index ? "copied" : "copy"}
            </button>
            {index < lines.length - 1 ? "\n\n" : ""}
          </span>
        ))}
      </pre>
    </div>
  );
}
