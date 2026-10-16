/** Under each of the agent's replies: copy it, say it was good, or say what was wrong with it — the record a person's correction will be kept as. */

import { useState, type ReactNode } from "react";

import { Button, Icon } from "../../ui";

// What a person says was wrong with ONE reply, in the words a reviewer would: each one points at
// what to fix — the prompt, the knowledge, a tool, the voice. The record it makes is the reply's
// segment id in its call, these reasons, and what it should have said: a golden written by a
// person who was there, which is what the agent is re-tested against.
const REASONS = ["Wrong information", "Didn't use a tool", "Wrong tool or arguments", "Made something up", "Ignored the caller", "Tone", "Too long"] as const;
type Reason = (typeof REASONS)[number];

// The gateway keeps no such record yet — there is no door for it, and this page may keep nothing of
// its own (the key is the one thing it stores). The form is drawn whole and Save waits for the door.
const NOT_YET = "The gateway does not keep a correction yet: this is the record it will take.";

/** The row of small buttons under a reply, and the correction form when the reply was bad. */
export function Feedback({ text }: { text: string }): ReactNode {
  const [copied, setCopied] = useState(false);
  const [verdict, setVerdict] = useState<"good" | "bad" | null>(null);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [expected, setExpected] = useState("");

  const copy = async (): Promise<void> => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  const toggle = (reason: Reason): void => setReasons(reasons.includes(reason) ? reasons.filter((one) => one !== reason) : [...reasons, reason]);

  return (
    <div className="talk-fb">
      <div className="talk-fb-row">
        <button type="button" className="talk-fb-btn" onClick={() => void copy()} data-tip={copied ? "Copied" : "Copy"} aria-label="Copy the reply">
          <Icon name={copied ? "check" : "copy"} size={15} />
        </button>
        <button type="button" className={verdict === "good" ? "talk-fb-btn talk-fb-on" : "talk-fb-btn"} onClick={() => setVerdict(verdict === "good" ? null : "good")} data-tip="Good reply" aria-pressed={verdict === "good"}>
          <Icon name="up" size={15} />
        </button>
        <button type="button" className={verdict === "bad" ? "talk-fb-btn talk-fb-on-bad" : "talk-fb-btn"} onClick={() => setVerdict(verdict === "bad" ? null : "bad")} data-tip="Bad reply — say what was wrong" aria-pressed={verdict === "bad"}>
          <Icon name="down" size={15} />
        </button>
      </div>
      {verdict === "bad" && (
        <div className="talk-fb-form">
          <div className="talk-fb-title">What was wrong with this reply?</div>
          <div className="talk-fb-reasons">
            {REASONS.map((reason) => (
              <button key={reason} type="button" className={reasons.includes(reason) ? "talk-fb-chip talk-fb-chip-on" : "talk-fb-chip"} onClick={() => toggle(reason)} aria-pressed={reasons.includes(reason)}>
                {reason}
              </button>
            ))}
          </div>
          <textarea className="talk-fb-text" rows={2} placeholder="What should it have said? It becomes the answer the agent is tested against." value={expected} onChange={(event) => setExpected(event.target.value)} />
          <div className="talk-fb-foot">
            <span className="talk-fb-note">{NOT_YET}</span>
            <Button size="sm" onClick={() => setVerdict(null)}>
              Cancel
            </Button>
            <Button size="sm" kind="primary" disabled data-tip={NOT_YET}>
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
