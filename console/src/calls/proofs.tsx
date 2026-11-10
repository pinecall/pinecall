/** Folded at the foot of the details: each confirmation joined to the tool call it authorised, and the prompt the call ran on, block by block. */

import { useMemo, useState, type ReactNode } from "react";

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { Icon } from "../shell/icons";

/** A tool call that required the caller's confirmation, and its confirmation entries. */
interface Consent {
  callId: string;
  tool: string;
  requested: Entry | null;
  granted: Entry | null;
  declined: Entry | null;
  ran: Entry | null;
}

function text(entry: Entry, field: string): string {
  const value = entry.data[field];
  return typeof value === "string" ? value : "";
}

// Matched by call_id, never by tool name: two bookings in one call each get their own grant.
function consents(entries: readonly Entry[]): Consent[] {
  const found = new Map<string, Consent>();
  for (const entry of entries) {
    if (!entry.type.startsWith("confirm.")) continue;
    const callId = text(entry, "call_id");
    const consent = found.get(callId) ?? { callId, tool: text(entry, "tool"), requested: null, granted: null, declined: null, ran: null };
    const part: Partial<Consent> = entry.type === "confirm.granted" ? { granted: entry } : entry.type === "confirm.declined" ? { declined: entry } : { requested: entry };
    found.set(callId, { ...consent, ...part });
  }
  for (const entry of entries) {
    const consent = entry.type === "tool.call" ? found.get(text(entry, "call_id")) : undefined;
    if (consent !== undefined) consent.ran = entry;
  }
  return [...found.values()];
}

function seqOf(entry: Entry | null): string {
  return entry === null ? "—" : String(entry.seq);
}

function joinOf(consent: Consent): string {
  if (consent.granted !== null) return `Seq ${consent.granted.seq} authorised seq ${seqOf(consent.ran)}`;
  return consent.declined === null ? `Seq ${seqOf(consent.requested)} asked and nothing answered` : `Seq ${seqOf(consent.declined)} declined seq ${seqOf(consent.ran)}`;
}

// The runtime's own three problems: shown, the console never fails a call.
function problemOf(consent: Consent): string | null {
  const { granted, ran, requested } = consent;
  if (granted === null || ran === null) return null;
  if (granted.seq > ran.seq) return `${consent.tool} ran at seq ${ran.seq}, before its confirmation at seq ${granted.seq}.`;
  const asked = requested === null ? null : text(requested, "audience");
  if (asked !== null && asked !== text(granted, "audience")) return `${consent.tool} was confirmed by another audience than the one asked at seq ${requested?.seq ?? 0}.`;
  return null;
}

function Proof({ consent }: { consent: Consent }): ReactNode {
  const problem = problemOf(consent);
  const audience = consent.granted ?? consent.declined ?? consent.requested;
  return (
    <div className="calls-proof">
      <span className="calls-tool-name">{consent.tool}</span>
      <span className="dash-quiet">{joinOf(consent)}</span>
      {consent.requested !== null && <p>{text(consent.requested, "phrase")}</p>}
      {consent.granted !== null && <p>“{text(consent.granted, "said")}”</p>}
      <span className="dash-quiet">Audience: {audience === null ? "—" : text(audience, "audience")}</span>
      {problem !== null && <p className="app-refused">{problem}</p>}
    </div>
  );
}

export function Proofs({ state, entries }: { state: State; entries: readonly Entry[] }): ReactNode {
  const [open, setOpen] = useState(false);
  const consented = useMemo(() => consents(entries), [entries]);
  const blocks = Object.entries(state.prompt);
  if (consented.length === 0 && blocks.length === 0) return null;
  return (
    <section className="calls-part" aria-label="Consent and prompt">
      <button type="button" className="ui-fold" aria-expanded={open} onClick={() => setOpen(!open)}>
        Consent and prompt
        <span>
          <Icon name="chevron" size={15} />
        </span>
      </button>
      {open && consented.length > 0 && (
        <div className="calls-proofs">
          <span className="dash-eyebrow">Consent</span>
          {consented.map((one) => (
            <Proof key={one.callId} consent={one} />
          ))}
        </div>
      )}
      {open && blocks.length > 0 && (
        <div className="calls-proofs">
          <span className="dash-eyebrow">The prompt, block by block</span>
          {blocks.map(([name, block]) => (
            <div key={name} className="calls-model">
              <span className="dash-quiet dash-clip">{name}</span>
              <span className="calls-model-name dash-clip">
                {block.chars} chars, seq {block.seq}
              </span>
            </div>
          ))}
          <p className="dash-quiet">By name and length: the text never enters the log. pinecall prompt --state prints it offline.</p>
        </div>
      )}
    </section>
  );
}
