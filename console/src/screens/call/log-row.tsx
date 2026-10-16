/** A call log row: seq, kind, text, optional note and expandable children. */

import type { ReactNode } from "react";

/** Row kinds; the tone sets the kind column and background colour. */
export type Tone = "turn" | "tool" | "state" | "confirm" | "event" | "supervisor" | "handing" | "quiet" | "lookup";

/** A row with children renders as `<details>`, the line being its summary. */
export function LogRow({
  seq,
  kind,
  tone,
  who,
  said,
  note = [],
  children,
}: {
  seq: number | undefined;
  kind: string;
  tone: Tone;
  who?: "caller" | "agent" | undefined;
  said: ReactNode;
  note?: ReactNode[];
  children?: ReactNode;
}): ReactNode {
  const shown = note.filter((one) => one !== null && one !== undefined && one !== "");
  const line = (
    <>
      <span className="call-seq">{seq}</span>
      <span className={`call-kind call-kind-${tone}`}>{kind}</span>
      <span className={tone === "turn" ? "call-text call-text-turn" : tone === "quiet" ? "call-text call-text-quiet" : "call-text"}>
        {who !== undefined && <span className={who === "agent" ? "call-who call-who-agent" : "call-who"}>{who}</span>}
        {said}
        {shown.length > 0 && (
          <span className="call-note">
            {shown.map((one, index) => (
              <span key={index}>
                {index > 0 && " · "}
                {one}
              </span>
            ))}
          </span>
        )}
      </span>
    </>
  );
  const ground = `call-row call-${tone}`;
  if (children === undefined || children === null || children === false) {
    return (
      <div className={ground}>
        <div className="call-line">{line}</div>
      </div>
    );
  }
  return (
    <details className={ground}>
      <summary className="call-line">{line}</summary>
      <div className="call-more">{children}</div>
    </details>
  );
}
