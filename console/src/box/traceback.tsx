/** Traceback, the operator's: one phone number looked up across every organization, to say whose it is, every call with it, kept or erased, and every time an agent dialled it. */

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { lengthOf } from "../lib/format";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Copy } from "../numbers/parts";
import { e164, shown } from "../numbers/words";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { readOrgs } from "./door";
import { readBoxNumbers, readTraceback, type Traceback, type TracedCall, type TracedDial } from "./telephony-door";
import { Head, OperatorPage, OrgLink, useDoor } from "./telephony-parts";

const DAY_S = 86400;
const EVERYTHING = "all";
const SPANS: readonly { value: string; label: string; detail?: string }[] = [
  { value: EVERYTHING, label: "Everything kept", detail: "The last 24 months" },
  { value: "365", label: "The last 12 months" },
  { value: "90", label: "The last 90 days" },
  { value: "30", label: "The last 30 days" },
  { value: "7", label: "The last 7 days" },
];

const RULES: readonly string[] = [
  "Only an operator can look a number up. The answer reads every organization, which no organization's own people can.",
  "Each look-up is written in the access log of every organization it showed, as read by the operator.",
  "A call still kept is shown from its facts. An erased call is shown as a record only: the two numbers, the times and how it ended. Never a name, never what was said.",
  "Records and dials are forgotten 24 months after the call.",
  "It exists to answer a carrier that asks who placed a call. Give the carrier the calls it asked about, and never show one organization the calls of another.",
];

function when(at: number | null | undefined): string {
  return at == null ? "Time unknown" : new Date(at * 1000).toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const plain = (code: string): string => code.replace(/_/g, " ");
const many = (count: number, one: string, more: string): string => `${count} ${count === 1 ? one : more}`;

function Board(): ReactNode {
  const credentials = useCredentials();
  const { whose } = useOrg();
  const [search] = useSearchParams();
  // Opened from a row of Routes, `?number=` is looked up on arrival.
  const arrived = search.get("number") ?? "";
  const [typed, setTyped] = useState(arrived);
  const [span, setSpan] = useState(EVERYTHING);
  const [found, setFound] = useState<Traceback | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // Both are a courtesy to the answer: whose the number is, and each org's name. Without them it still reads.
  const numbers = useDoor(useCallback(() => readBoxNumbers(credentials).catch(() => []), [credentials]));
  const orgs = useDoor(useCallback(() => readOrgs(credentials).catch(() => []), [credentials]));

  const lookUp = useCallback(
    (number: string, days: string): void => {
      if (number === "") return;
      setBusy(true);
      setRefused(null);
      readTraceback(credentials, number, days === EVERYTHING ? null : Math.floor(Date.now() / 1000) - Number(days) * DAY_S)
        .then(setFound, (failed: unknown) => (setFound(null), setRefused(saidBy(failed))))
        .finally(() => setBusy(false));
    },
    [credentials],
  );
  useEffect(() => lookUp(e164(arrived), EVERYTHING), [lookUp, arrived]);

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    lookUp(e164(typed), span);
  };

  // A call names its org by id and a route by slug: either finds it.
  const orgOf = useMemo(() => {
    const known = new Map((orgs.value ?? []).flatMap((one) => [[one.id, one] as const, [one.slug, one] as const]));
    return (named: string | null | undefined): ReactNode => {
      if (named == null) return "An organization since removed";
      const org = known.get(named);
      return org === undefined ? named : <OrgLink slug={org.slug} name={org.name} />;
    };
  }, [orgs.value]);

  const owners = found === null ? [] : (numbers.value ?? []).filter((row) => row.number === found.number);
  const involved = found === null ? 0 : new Set([...found.calls.map((call) => call.org), ...found.dials.map((dial) => dial.org)].filter((one) => one != null)).size;
  // A call opens on the Calls page only where that page can read it: this org, this environment, not erased.
  const opens = (call: TracedCall): boolean => !call.erased && call.env === WORLD && call.org != null && (call.org === whose?.org || call.org === whose?.slug);

  const callRow = (call: TracedCall): ReactNode => (
    <div key={call.call} className="tst-row tel-row">
      <span className="tst-row-words">
        <span className="tst-row-name">
          <span className="dash-clip">
            {shown(call.from_number ?? null)} called {shown(call.to_number ?? null)}
          </span>
          {call.direction != null && <span className="tst-tag">{call.direction}</span>}
          {call.env != null && <span className="tst-tag">{call.env}</span>}
        </span>
        <span className="tst-row-under">
          {orgOf(call.org)}. {when(call.started_at)}, lasted {lengthOf(call.started_at ?? null, call.ended_at ?? null)}
          {call.end_reason == null ? "" : `, ended: ${plain(call.end_reason)}`}.
        </span>
        <span className="tst-row-under tel-id">
          <Copy text={call.call} bare />
        </span>
      </span>
      <span className={`tst-status tst-status-${call.erased ? "none" : "held"} tel-status`} title={call.erased ? "The organization erased this call. Only its numbers, times and ending are left." : "The organization still keeps this call."}>
        {call.erased ? "Record only" : "Kept"}
      </span>
      {opens(call) && (
        <Link to={`/calls/${encodeURIComponent(call.call)}`} className="app-button tel-go">
          Open the call
        </Link>
      )}
    </div>
  );

  const dialRow = (dial: TracedDial, index: number): ReactNode => (
    <div key={`${dial.at} ${index}`} className="tst-row tel-row">
      <span className="tst-row-words">
        <span className="tst-row-name">
          <span className="dash-clip">{dial.agent} dialled it</span>
          <span className="tst-tag">{dial.env}</span>
        </span>
        <span className="tst-row-under">
          {orgOf(dial.org)}. {when(dial.at)}, asked by {dial.asked_by}
          {dial.shown == null ? "" : `, showing ${shown(dial.shown)} as the caller`}.
        </span>
        {dial.refused != null && <span className="tst-row-under tel-why">Not placed: {dial.refused}</span>}
        {dial.refused == null && dial.call != null && (
          <span className="tst-row-under tel-id">
            <Copy text={dial.call} bare />
          </span>
        )}
      </span>
      <span className={`tst-status tst-status-${dial.refused == null ? "held" : "broke"} tel-status`}>{dial.refused == null ? "Placed" : "Refused"}</span>
    </div>
  );

  return (
    <>
      <section className="tst-list" aria-label="Look a number up">
        <Head icon="search" title="Look a number up" about="Type any phone number: one of yours, or one that called or was called. You get whose it is, every call with it in every organization, and every time an agent dialled it." />
        <form className="tel-look" onSubmit={submit}>
          <input className="cfg-input tel-look-number" aria-label="Phone number" placeholder="+1 415 555 0142, with its country code" autoFocus autoComplete="off" value={typed} onChange={(event) => setTyped(event.target.value)} />
          <div className="tel-pick">
            <Select label="How far back" searchable={false} items={SPANS} value={span} onChange={setSpan} />
          </div>
          <button type="submit" className="cfg-save tel-look-go" disabled={busy || typed.trim() === ""}>
            <Icon name="search" size={13} />
            {busy ? "Looking…" : "Look up"}
          </button>
        </form>
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}
      </section>

      {found !== null && (
        <>
          <section className="dash-card tel-answer" aria-label="The answer">
            <span className="dash-eyebrow">The answer</span>
            <span className="tel-answer-number">{shown(found.number)}</span>
            {owners.length === 0 ? (
              <p className="tel-answer-line">Not a number this deployment answers. It is somebody who called, or was called.</p>
            ) : (
              owners.map((row) => (
                <p key={`${row.org} ${row.env} ${row.channel}`} className="tel-answer-line">
                  It belongs to {orgOf(row.org)}: {row.agent} answers it in {row.env}
                  {row.channel === "phone" ? "" : `, on ${row.channel}`}.
                </p>
              ))
            )}
            <p className="dash-quiet">
              {found.calls.length === 0 && found.dials.length === 0 ? `No call and no dial since ${when(found.since)}.` : `${many(found.calls.length, "call", "calls")} and ${many(found.dials.length, "dial", "dials")} since ${when(found.since)}, in ${many(involved, "organization", "organizations")}.`}
            </p>
          </section>

          <section className="tst-list" aria-label="Calls">
            <Head icon="calls" title="Calls with this number" about="Every phone call it made or received here, oldest first, whichever organization's.">
              <span className="tst-head-stands">{found.calls.length}</span>
            </Head>
            {found.calls.map(callRow)}
            {found.calls.length === 0 && <p className="dash-quiet tst-none">No phone call with this number.</p>}
          </section>

          <section className="tst-list" aria-label="Dials">
            <Head icon="arrow" title="Times an agent dialled it" about="Every attempt to call this number out, whether it was placed or refused, and who asked for it.">
              <span className="tst-head-stands">{found.dials.length}</span>
            </Head>
            {found.dials.map(dialRow)}
            {found.dials.length === 0 && <p className="dash-quiet tst-none">No agent ever dialled this number.</p>}
          </section>
        </>
      )}

      <section className="tst-list" aria-label="Who may be shown what">
        <Head icon="privacy" title="Who may be shown what" about="A traceback crosses every organization's calls. These are its limits." />
        <ul className="tel-rules">
          {RULES.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

export function TracebackPage(): ReactNode {
  return (
    <OperatorPage>
      <Board />
    </OperatorPage>
  );
}
