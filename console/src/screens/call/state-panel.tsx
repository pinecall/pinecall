/** State panel: the app's state fields from the last state.changed, with their visibility. */

import type { ReactNode } from "react";

import type { Visibility } from "../../lib/declared-state";
import { KV, SectionLabel } from "../../ui";

// Platform-wide mask for PII values (runtime log/pii.py, docs/protocol/projections.md).
const MASK = "***";

// Undeclared fields default to tenant visibility (AgentConfig.visibility_of).
const BY_DEFAULT: Visibility = "tenant";

export function StatePanel({ fields, declared }: { fields: Record<string, unknown>; declared: Record<string, Visibility> }): ReactNode {
  const names = Object.keys(fields).sort();
  return (
    <>
      <SectionLabel>State</SectionLabel>
      {names.length === 0 ? (
        <div className="call-pane-text">The app has declared no state yet.</div>
      ) : (
        <div className="call-pane-body">
          {names.map((name) => {
            const seen = seenBy(fields[name], declared[name]);
            return (
              <KV key={name} label={name}>
                {said(fields[name])}
                {/* Only non-default visibilities get a label. */}
                {seen !== BY_DEFAULT && <span className={seen === "pii" ? "call-seen call-seen-pii" : "call-seen"}>{seen}</span>}
              </KV>
            );
          })}
        </div>
      )}
    </>
  );
}

// PII fields always arrive masked, so the mask identifies them; the rest come from the declaration.
function seenBy(value: unknown, declared: Visibility | undefined): Visibility {
  if (value === MASK) {
    return "pii";
  }
  return declared === "public" ? "public" : BY_DEFAULT;
}

function said(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}
