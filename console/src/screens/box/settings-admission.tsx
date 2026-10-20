/** Admission: what a newborn org is given in each world — its limits, and the runtime's keys it may run on. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, Refused, Segmented } from "../../ui";
import { QUOTAS, type Quota } from "./door";
import { readAdmission, readBoxVendors, saveAdmission, type Admission, type NewbornQuotas } from "./door-box";
import { LendsPicker } from "./lends";
import { ABOUT } from "./org-limits";
import { useDoor, useMove } from "./use-door";

const WORLDS = [
  { value: "sandbox", label: "Sandbox" },
  { value: "production", label: "Production" },
] as const;

const WHOSE = [
  { value: "first", label: "First org of a person" },
  { value: "later", label: "Second org onwards" },
] as const;

type World = (typeof WORLDS)[number]["value"];
type Whose = (typeof WHOSE)[number]["value"];

const digits = (typed: string): string => typed.replace(/[^0-9]/g, "");

/** The fields of one world's row as typed: a number, or "" for no limit. */
export function typedOf(quotas: NewbornQuotas | undefined): Record<string, string> {
  return Object.fromEntries(QUOTAS.map((quota) => [quota, typeof quotas?.[quota] === "number" ? String(quotas[quota]) : ""]));
}

/** The row written back: this world's limits and lends replaced, everything else as it was. */
export function withWorld(row: Admission, whose: Whose, world: World, typed: Record<string, string>, lends: string[] | null): Admission {
  const limits: NewbornQuotas = Object.fromEntries(
    QUOTAS.filter((quota) => typed[quota] !== undefined && typed[quota] !== "").map((quota) => [quota, Number(typed[quota])]),
  );
  const side = { ...((whose === "first" ? row.first : row.later) ?? {}), [world]: { ...limits, lends } };
  return whose === "first" ? { ...row, first: side } : { ...row, later: side };
}

/**
 * Read at the moment an org is made: the orgs already made keep their quotas. Minutes, messages,
 * tokens, evals and simulations are a month's, and start again on the first (UTC).
 */
export function SettingsAdmission(): ReactNode {
  const credentials = useCredentials();
  const admission = useDoor(useCallback(() => readAdmission(credentials), [credentials]));
  const vendors = useDoor(useCallback(() => readBoxVendors(credentials), [credentials]));
  const acting = useMove();
  const [world, setWorld] = useState<World>("sandbox");
  const [whose, setWhose] = useState<Whose>("first");
  const [typed, setTyped] = useState<Record<string, string> | null>(null);
  const [lends, setLends] = useState<string[] | null | undefined>(undefined);
  const [saved, setSaved] = useState(false);

  if (admission.value === undefined) return <Refused>{admission.refused}</Refused>;
  const row = admission.value;
  const standing = (whose === "first" ? row.first : row.later ?? {})[world];
  const shown = typed ?? typedOf(standing);
  const lent = lends === undefined ? ((standing?.["lends"] as string[] | null | undefined) ?? null) : lends;
  const reset = (): void => {
    setTyped(null);
    setLends(undefined);
    setSaved(false);
  };

  const save = async (): Promise<void> => {
    const done = await acting.move(async () => {
      await saveAdmission(credentials, withWorld(row, whose, world, shown, lent));
      await admission.reread();
    });
    if (done) {
      reset();
      setSaved(true);
    }
  };

  return (
    <Card>
      <CardHead title="Starting limits for new orgs" meta="Set once, when an org is created. Orgs that already exist are not touched." />
      <div className="box-body">
        <div className="box-line">
          <Segmented options={WHOSE} value={whose} onChange={(picked) => { setWhose(picked); reset(); }} />
          <Segmented options={WORLDS} value={world} onChange={(picked) => { setWorld(picked); reset(); }} />
        </div>
        <div className="box-limit-about">
          {whose === "later" && row.later === null
            ? "Not set: a person's second org and later get the same as their first."
            : `Limits a new ${world} org starts with${whose === "later" ? ", when its creator already has an org" : ", when its creator has no org yet"}. Monthly limits reset on the 1st, UTC.`}
          {" "}Leave a box empty for unlimited; type 0 to block it entirely.
        </div>
      </div>
      <div className="box-limits">
        {QUOTAS.map((quota: Quota) => (
          <Field key={quota} label={ABOUT[quota].name}>
            <Input inputMode="numeric" value={shown[quota] ?? ""} placeholder="unlimited" onChange={(event) => setTyped({ ...shown, [quota]: digits(event.target.value) })} />
            <div className="box-limit-about">{ABOUT[quota].about}</div>
          </Field>
        ))}
      </div>
      <div className="box-body">
        <Field label="The runtime's keys these orgs may use">
          <LendsPicker key={`${whose}:${world}`} vendors={vendors.value ?? []} lends={lent} onChange={setLends} />
        </Field>
      </div>
      <div className="box-save">
        <Button kind="primary" size="md" disabled={acting.busy} onClick={() => void save()}>
          {acting.busy ? "Saving…" : "Save for new orgs"}
        </Button>
        {saved && <span className="box-done">Saved. The next org made gets it; the ones already made keep theirs.</span>}
      </div>
      <Refused>{acting.refused}</Refused>
    </Card>
  );
}
