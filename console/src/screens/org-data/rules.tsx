/** The org's rules card: how long a call is kept, the hours a number is rung, how often, and where consent is asked. */

import { useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { Button, Card, CardHead, Input, Select, SelectItem } from "../../ui";
import { putPolicy, NOTHING_SET, type Policy, type PolicyRow } from "./door";

const HOURS = Array.from({ length: 25 }, (_, hour) => hour);

/** The org's rules: how long a call is kept, the called number's hours, calls a day per number, consent. */
export function RulesCard({ policy, onSaved, onRefused }: { policy: PolicyRow | null; onSaved: (row: PolicyRow) => void; onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const [days, setDays] = useState("");
  const [count, setCount] = useState("");
  const [busy, setBusy] = useState(false);
  const kept = policy?.policy ?? NOTHING_SET;
  const hours = kept.calling_hours ?? null;

  const save = async (changes: Partial<Policy>): Promise<void> => {
    setBusy(true);
    onRefused(null);
    try {
      onSaved(await putPolicy(credentials, kept, changes));
      setDays("");
      setCount("");
    } catch (failed) {
      onRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const aCount = (typed: string, what: string): number | undefined => {
    const wanted = Number(typed);
    if (Number.isInteger(wanted) && wanted >= 1) return wanted;
    onRefused(`${what} is a whole number, 1 or more.`);
    return undefined;
  };

  const saveDays = (event: FormEvent): void => {
    event.preventDefault();
    const wanted = aCount(days, "Retention");
    if (wanted !== undefined) void save({ retention_days: wanted });
  };

  const saveCount = (event: FormEvent): void => {
    event.preventDefault();
    const wanted = aCount(count, "The count");
    if (wanted !== undefined) void save({ per_number_day: wanted });
  };

  const saveHours = (from: number, until: number): void => {
    if (from >= until) {
      onRefused("Calling hours are a window of the day: from before until.");
      return;
    }
    void save({ calling_hours: { from, until } });
  };

  const setBy = policy?.set_by ? `set by ${policy.set_by}${policy.set_at === null ? "" : ` · ${dayAndTime(policy.set_at)}`}` : "nobody set it";

  return (
    <Card pad>
      <CardHead title="Rules" meta={setBy} />

      <p className="data-sentence">
        <b>Retention.</b>{" "}
        {kept.retention_days == null ? "Every sealed call is kept until somebody erases it." : `A sealed call is erased ${kept.retention_days} day${kept.retention_days === 1 ? "" : "s"} after it started, by the box's run at 04:00.`}
      </p>
      <form className="data-form" onSubmit={saveDays}>
        <label className="ui-label" htmlFor="data-days">Keep a call for</label>
        <Input id="data-days" value={days} inputMode="numeric" placeholder={kept.retention_days == null ? "365" : String(kept.retention_days)} onChange={(event) => setDays(event.target.value)} />
        <span className="data-unit">days</span>
        <Button type="submit" kind="primary" size="form" disabled={busy || days === ""}>Save</Button>
        {kept.retention_days != null && <Button size="form" disabled={busy} onClick={() => void save({ retention_days: null })}>Keep everything</Button>}
      </form>

      <p className="data-sentence data-sentence-next">
        <b>Calling hours.</b>{" "}
        {hours === null ? "A number is rung at any hour of its own day; a US or Canadian number from 8:00 to 21:00 whatever is set here." : `A number is rung from ${hours.from}:00 to ${hours.until}:00 of its own day; a US or Canadian number never before 8:00 or after 21:00.`}
        {" "}The sandbox and your own verified phone are never held to them.
      </p>
      <div className="data-form">
        <label className="ui-label" htmlFor="data-from">From</label>
        <Select id="data-from" className="data-hour" aria-label="From" value={String(hours?.from ?? 8)} disabled={busy} onValueChange={(value) => saveHours(Number(value), hours?.until ?? 21)}>
          {HOURS.slice(0, 24).map((hour) => <SelectItem key={hour} value={String(hour)}>{hour}:00</SelectItem>)}
        </Select>
        <label className="ui-label" htmlFor="data-until">until</label>
        <Select id="data-until" className="data-hour" aria-label="Until" value={String(hours?.until ?? 21)} disabled={busy} onValueChange={(value) => saveHours(hours?.from ?? 8, Number(value))}>
          {HOURS.slice(1).map((hour) => <SelectItem key={hour} value={String(hour)}>{hour}:00</SelectItem>)}
        </Select>
        {hours !== null && <Button size="form" disabled={busy} onClick={() => void save({ calling_hours: null })}>Any hour</Button>}
      </div>

      <p className="data-sentence data-sentence-next">
        <b>Calls to one number a day.</b>{" "}
        {kept.per_number_day == null ? "No limit of the org's own; a US or Canadian number is rung at most three times in 24 hours." : `One number is rung at most ${kept.per_number_day} time${kept.per_number_day === 1 ? "" : "s"} in 24 hours.`}
      </p>
      <form className="data-form" onSubmit={saveCount}>
        <label className="ui-label" htmlFor="data-count">At most</label>
        <Input id="data-count" value={count} inputMode="numeric" placeholder={kept.per_number_day == null ? "3" : String(kept.per_number_day)} onChange={(event) => setCount(event.target.value)} />
        <span className="data-unit">calls a day</span>
        <Button type="submit" kind="primary" size="form" disabled={busy || count === ""}>Save</Button>
        {kept.per_number_day != null && <Button size="form" disabled={busy} onClick={() => void save({ per_number_day: null })}>No limit</Button>}
      </form>

      <p className="data-sentence data-sentence-next">
        <b>Consent in every country.</b>{" "}
        {kept.consent_everywhere === true
          ? "A call to any number in production needs a consent on file or sent with the dial."
          : "A call to a US or Canadian number in production needs a consent on file; other countries do not, unless this is on."}
      </p>
      <Button size="form" disabled={busy} onClick={() => void save({ consent_everywhere: kept.consent_everywhere !== true })}>
        {kept.consent_everywhere === true ? "Only where the law asks" : "Ask for consent everywhere"}
      </Button>
    </Card>
  );
}
