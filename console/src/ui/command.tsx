/** One terminal command on a line of its own, copied with a click. */

import { useState, type ReactNode } from "react";

import { Icon } from "./icon";

export function Command({ run }: { run: string }): ReactNode {
  const [copied, setCopied] = useState(false);
  const copy = (): void => {
    navigator.clipboard.writeText(run).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
      },
      () => undefined,
    );
  };
  return (
    <button type="button" className="ui-command" onClick={copy} title="Copy">
      <span className="ui-command-prompt">$</span>
      <span className="ui-command-run">{run}</span>
      <span className="ui-command-copy">{copied ? "copied" : <Icon name="copy" size={13} />}</span>
    </button>
  );
}
