/** Consent proof: joins each confirm.granted to the tool call it authorised. */

import { type Entry } from "@pinecall/core/wire/envelope";
import type { ReactNode } from "react";

// Same join as the runtime's api/evals/consent.py: match by call_id, never tool name (two bookings
// in one call each get their own grant). Display only: irreversibility is declared by the app, not the log.
const CONFIRM_PREFIX = "confirm.";
const TOOL_CALL = "tool.call";

/** A tool call that required caller confirmation, and its confirmation entries. */
export interface Consent {
  callId: string;
  tool: string;
  requested: Entry | null;
  granted: Entry | null;
  declined: Entry | null;
  ran: Entry | null;
}

/** Every confirmation joined to its tool call, in request order. */
export function consents(entries: Entry[]): Consent[] {
  const found = new Map<string, Consent>();
  for (const entry of entries) {
    if (!entry.type.startsWith(CONFIRM_PREFIX)) {
      continue;
    }
    const callId = text(entry, "call_id");
    const consent = found.get(callId) ?? blank(callId, text(entry, "tool"));
    found.set(callId, { ...consent, ...asked(entry) });
  }
  for (const entry of entries) {
    const consent = entry.type === TOOL_CALL ? found.get(text(entry, "call_id")) : undefined;
    if (consent !== undefined) {
      consent.ran = entry;
    }
  }
  return [...found.values()];
}

export function Consents({ rows }: { rows: Consent[] }): ReactNode {
  if (rows.length === 0) {
    return null;
  }
  return (
    <div className="over-consents">
      {rows.map((row) => (
        <Proof key={row.callId} consent={row} />
      ))}
    </div>
  );
}

function Proof({ consent }: { consent: Consent }): ReactNode {
  const problem = problemOf(consent);
  return (
    <div className="over-consent">
      <div className="over-consent-join">
        <span className="over-consent-tool">{consent.tool}</span>
        <span className="over-consent-seqs">{joinOf(consent)}</span>
        <span className="over-consent-id ui-fixed">{consent.callId}</span>
      </div>
      {consent.requested !== null && <div className="over-consent-said">{text(consent.requested, "phrase")}</div>}
      {consent.granted !== null && <div className="over-consent-said">“{text(consent.granted, "said")}”</div>}
      <div className="over-consent-audience">audience {audienceOf(consent)}</div>
      {problem !== null && <div className="ui-refused">{problem}</div>}
    </div>
  );
}

function joinOf(consent: Consent): string {
  if (consent.granted === null) {
    return consent.declined === null
      ? `seq ${seqOf(consent.requested)} asked and nothing answered`
      : `seq ${seqOf(consent.declined)} declined seq ${seqOf(consent.ran)}`;
  }
  return `seq ${consent.granted.seq} authorised seq ${seqOf(consent.ran)}`;
}

// consent.py's three problems, verbatim. Shown only; the console never fails a call.
function problemOf(consent: Consent): string | null {
  const { granted, ran, requested } = consent;
  if (granted === null || ran === null) {
    return null;
  }
  if (granted.seq > ran.seq) {
    return `${consent.tool} ran at seq ${ran.seq}, before its confirm.granted at seq ${granted.seq}`;
  }
  const asked = requested === null ? null : text(requested, "audience");
  if (asked !== null && asked !== text(granted, "audience")) {
    return `${consent.tool} was confirmed by another audience than the one asked at seq ${requested?.seq ?? 0}`;
  }
  return null;
}

function audienceOf(consent: Consent): string {
  const entry = consent.granted ?? consent.declined ?? consent.requested;
  return entry === null ? "—" : text(entry, "audience");
}

function asked(entry: Entry): Partial<Consent> {
  if (entry.type === "confirm.granted") {
    return { granted: entry };
  }
  return entry.type === "confirm.declined" ? { declined: entry } : { requested: entry };
}

function blank(callId: string, tool: string): Consent {
  return { callId, tool, requested: null, granted: null, declined: null, ran: null };
}

function seqOf(entry: Entry | null): string {
  return entry === null ? "—" : String(entry.seq);
}

function text(entry: Entry, field: string): string {
  const value = entry.data[field];
  return typeof value === "string" ? value : "";
}
