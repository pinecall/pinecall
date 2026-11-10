/** The Rules tab: how long calls are kept, when and how often a number is rung, where consent is asked, and what a call says first; one Save. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../lib/format";
import { Select } from "../ui/select";
import { Setting, Toggle } from "../ui/setting";
import { putPolicy, readPolicy, type Policy, type PolicyRow } from "./door";
import { Head, whoOf, type Names } from "./parts";

const THE_PLATFORMS = "This is an automated assistant calling on behalf of {your organization}.";
const FROM_HOURS = Array.from({ length: 24 }, (_, hour) => ({ value: String(hour), label: `${hour}:00` }));
const UNTIL_HOURS = Array.from({ length: 24 }, (_, hour) => ({ value: String(hour + 1), label: `${hour + 1}:00` }));

type Opening = "platform" | "own" | "none";
const OPENINGS: readonly { value: Opening; name: string }[] = [
  { value: "platform", name: "Pinecall's sentence" },
  { value: "own", name: "Your own words" },
  { value: "none", name: "Nothing" },
];

/** The policy as the form holds it: a number typed is a string, and an empty one is "not set". */
interface Draft {
  days: string;
  limited: boolean;
  from: number;
  until: number;
  perDay: string;
  everywhere: boolean;
  opening: Opening;
  words: string;
  notice: boolean;
}

function draftOf(policy: Policy): Draft {
  const disclosure = policy.disclosure ?? null;
  return {
    days: policy.retention_days == null ? "" : String(policy.retention_days),
    limited: policy.calling_hours != null,
    from: policy.calling_hours?.from ?? 8,
    until: policy.calling_hours?.until ?? 21,
    perDay: policy.per_number_day == null ? "" : String(policy.per_number_day),
    everywhere: policy.consent_everywhere === true,
    opening: disclosure === null ? "platform" : disclosure === "" ? "none" : "own",
    words: disclosure ?? "",
    notice: policy.recording_notice !== false,
  };
}

// Null for an empty field; undefined for what is no whole number from 1 up.
function countOf(typed: string): number | null | undefined {
  if (typed.trim() === "") return null;
  const wanted = Number(typed);
  return Number.isInteger(wanted) && wanted >= 1 ? wanted : undefined;
}

/** The draft as the gateway keeps it, or the sentence that says what is wrong with it. */
function policyOf(draft: Draft): Partial<Policy> | string {
  const days = countOf(draft.days);
  if (days === undefined) return "Retention is a whole number of days, 1 or more. Leave it empty to keep calls forever.";
  const perDay = countOf(draft.perDay);
  if (perDay === undefined) return "Calls a day is a whole number, 1 or more. Leave it empty for no limit.";
  if (draft.limited && draft.from >= draft.until) return "Calling hours start before they end.";
  if (draft.opening === "own" && draft.words.trim() === "") return "Write the sentence the agent says first.";
  return {
    retention_days: days,
    calling_hours: draft.limited ? { from: draft.from, until: draft.until } : null,
    per_number_day: perDay,
    consent_everywhere: draft.everywhere,
    disclosure: draft.opening === "platform" ? null : draft.opening === "none" ? "" : draft.words.trim(),
    recording_notice: draft.notice,
  };
}

export function RulesTab({ names }: { names: Names }): ReactNode {
  const credentials = useCredentials();
  const [row, setRow] = useState<PolicyRow | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readPolicy(credentials).then((kept) => !gone && (setRow(kept), setDraft(draftOf(kept.policy))), (failed: unknown) => !gone && setRefused(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials]);

  if (row === null || draft === null) {
    return refused === null ? (
      <p className="dash-quiet">Reading…</p>
    ) : (
      <p className="cfg-refused" role="alert">
        {refused}
      </p>
    );
  }

  const change = (changes: Partial<Draft>): void => setDraft({ ...draft, ...changes });
  const changed = JSON.stringify(draft) !== JSON.stringify(draftOf(row.policy));

  const save = async (): Promise<void> => {
    const wanted = policyOf(draft);
    if (typeof wanted === "string") return setRefused(wanted);
    setSaving(true);
    setRefused(null);
    try {
      const kept = await putPolicy(credentials, row.policy, wanted);
      setRow(kept);
      setDraft(draftOf(kept.policy));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="tst-list tst-tone-blue" aria-label="Keeping and calling">
        <Head icon="clock" title="Keeping and calling" about="How long a call is kept, and when a number may be rung." />
        <div className="prv-settings">
          <Setting
            icon="clock"
            title="Keep calls for"
            about="A call older than this is erased overnight, with its log and recording. Empty keeps every call."
            aside={
              <span className="prv-amount">
                <input className="cfg-input" inputMode="numeric" aria-label="Days a call is kept" placeholder="Forever" value={draft.days} onChange={(event) => change({ days: event.target.value })} />
                <span className="prv-unit">days</span>
              </span>
            }
          />
          <Setting
            icon="sun"
            title="Calling hours"
            about="The hours of the called number's own day. A US or Canadian number is never rung before 8:00 or after 21:00."
            aside={<Toggle on={draft.limited} label="Limit calling hours" onChange={(limited) => change({ limited })} />}
          >
            {draft.limited && (
              <div className="prv-hours">
                <span>From</span>
                <Select label="From" items={FROM_HOURS} value={String(draft.from)} onChange={(value) => change({ from: Number(value) })} />
                <span>until</span>
                <Select label="Until" items={UNTIL_HOURS} value={String(draft.until)} onChange={(value) => change({ until: Number(value) })} />
              </div>
            )}
          </Setting>
          <Setting
            icon="hash"
            title="Calls a day per number"
            about="The most one number is rung in 24 hours. Empty sets no limit; a US or Canadian number gets three at most."
            aside={
              <span className="prv-amount">
                <input className="cfg-input" inputMode="numeric" aria-label="Calls a day per number" placeholder="No limit" value={draft.perDay} onChange={(event) => change({ perDay: event.target.value })} />
                <span className="prv-unit">calls a day</span>
              </span>
            }
          />
          <Setting
            icon="check"
            title="Consent in every country"
            about={draft.everywhere ? "A production call to any number needs a consent on file." : "Only US and Canadian numbers need a consent on file."}
            aside={<Toggle on={draft.everywhere} label="Consent required everywhere" onChange={(everywhere) => change({ everywhere })} />}
          />
        </div>
      </section>

      <section className="tst-list prv-tone-pink" aria-label="What a call says first">
        <Head icon="chat" title="What a call says first" about="Said in the agent's voice before its greeting, and kept as the call's first turn." />
        <div className="prv-settings">
          <Setting icon="chat" title="Disclosure" about="What an outbound call opens with.">
            <div className="dash-switch prv-opening" role="group" aria-label="Disclosure">
              {OPENINGS.map((one) => (
                <button key={one.value} type="button" aria-pressed={draft.opening === one.value} className={draft.opening === one.value ? "dash-switch-on" : ""} onClick={() => change({ opening: one.value })}>
                  {one.name}
                </button>
              ))}
            </div>
            {draft.opening === "platform" && <p className="prv-said">“{THE_PLATFORMS}” In the agent's language.</p>}
            {draft.opening === "own" && <textarea className="cfg-input cfg-area" rows={2} maxLength={500} aria-label="Your own opening sentence" placeholder="Hi, this is Ana, Clínica Norte's virtual assistant." value={draft.words} onChange={(event) => change({ words: event.target.value })} />}
            {draft.opening === "none" && <p className="prv-warn">The agent's own greeting must then say it is automated, and whom it calls for. Some US states require it.</p>}
          </Setting>
          <Setting
            icon="speaker"
            title="Recording notice"
            about={draft.notice ? "A recorded call says “This call may be recorded.”" : "A recorded call says nothing of it. All-party states need the caller told."}
            aside={<Toggle on={draft.notice} label="Recording notice" onChange={(notice) => change({ notice })} />}
          />
        </div>
      </section>

      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      <footer className="prv-save">
        <span className="dash-quiet">{row.set_by == null ? "Nobody has set these yet." : `Last set by ${whoOf(names, row.set_by)}${row.set_at == null ? "" : `, ${ago(row.set_at)}`}.`}</span>
        {changed && (
          <button type="button" className="app-button" disabled={saving} onClick={() => (setDraft(draftOf(row.policy)), setRefused(null))}>
            Discard
          </button>
        )}
        <button type="button" className="cfg-save" disabled={saving || !changed} onClick={() => void save()}>
          {saving ? "Saving…" : "Save"}
        </button>
      </footer>
    </>
  );
}
