/** An org's quotas, what the box lends it of its keys, and its outbound-call limits. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, Refused, Segmented, Switch } from "../../ui";
import { QUOTAS, saveDialling, saveQuotas, type OneOrg, type Quota } from "./door";
import { readBoxVendors } from "./door-box";
import { LendsPicker } from "./lends";
import { useDoor, useMove } from "./use-door";

export const ABOUT: Record<Quota, { name: string; about: string }> = {
  minutes: { name: "Minutes", about: "Call minutes per month" },
  messages: { name: "Messages", about: "Chat messages per month" },
  llm_tokens: { name: "Model tokens", about: "Model tokens per month, read and written" },
  agents: { name: "Agents", about: "Agents the org can have" },
  concurrent_calls: { name: "Concurrent calls", about: "Calls running at the same time" },
  memory_facts: { name: "Memory facts", about: "Facts remembered about callers" },
  knowledge_chunks: { name: "Knowledge chunks", about: "Pieces of text indexed from knowledge bases" },
  numbers: { name: "Numbers", about: "Phone numbers bought through Pinecall" },
  seats: { name: "Seats", about: "People in the org, invited or active" },
  hosted_apps: { name: "Hosted apps", about: "Apps Pinecall runs for the org" },
  evals: { name: "Evals", about: "Judge runs per month, on the runtime's keys" },
  simulations: { name: "Simulations", about: "Simulated test calls per month" },
  budget_usd: { name: "Budget, $", about: "Spend cap per month, both worlds" },
};

const WORLDS = [
  { value: "production", label: "Production" },
  { value: "sandbox", label: "Sandbox" },
] as const;

/** One world's limits as the fields hold them: a number typed, or "" for no limit. */
function typedOf(org: OneOrg, env: string): Record<string, string> {
  const world = org.quotas[env];
  const of = (quota: Quota): number | null | undefined => (quota === "budget_usd" ? world?.budget_usd : world?.limits[quota]);
  return Object.fromEntries(QUOTAS.map((quota) => [quota, of(quota) === null || of(quota) === undefined ? "" : String(of(quota))]));
}

const HELD: Partial<Record<Quota, keyof OneOrg["holding"]>> = { memory_facts: "memory_facts", knowledge_chunks: "knowledge_chunks", numbers: "numbers", seats: "seats" };

const digits = (typed: string): string => typed.replace(/[^0-9]/g, "");

/**
 * Both panels replace their set whole. Empty means no limit; `0` refuses everything.
 * Dialable countries are the carrier account's setting, not ours.
 */
export function OrgLimits({ org, onSaved }: { org: OneOrg; onSaved: () => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const quotas = useMove();
  const dialling = useMove();
  const [env, setEnv] = useState<"production" | "sandbox">("production");
  const [wanted, setWanted] = useState<Record<string, string>>(() => typedOf(org, "production"));
  const [lends, setLends] = useState<string[] | null>(org.quotas["production"]?.lends ?? null);
  const vendors = useDoor(useCallback(() => readBoxVendors(credentials), [credentials]));
  const [saved, setSaved] = useState<"quotas" | "dialling" | null>(null);
  const guards = org.dialling ?? null;
  const [anywhere, setAnywhere] = useState(guards?.dial_anywhere ?? false);
  const [perMinute, setPerMinute] = useState(String(guards?.per_minute ?? ""));
  const [perDay, setPerDay] = useState(String(guards?.per_day ?? ""));
  const [longest, setLongest] = useState(String(guards?.max_duration_s ?? ""));

  const saveLimits = async (): Promise<void> => {
    setSaved(null);
    const done = await quotas.move(async () => {
      const number = (quota: Quota): number | null => (wanted[quota] === "" || wanted[quota] === undefined ? null : Number(wanted[quota]));
      const limits = Object.fromEntries(QUOTAS.filter((quota) => quota !== "budget_usd").map((quota) => [quota, number(quota)]));
      await saveQuotas(credentials, org.slug, env, { limits, budget_usd: number("budget_usd"), lends });
      await onSaved();
    });
    if (done) setSaved("quotas");
  };

  const saveGuards = async (): Promise<void> => {
    setSaved(null);
    const done = await dialling.move(async () => {
      await saveDialling(credentials, org.slug, {
        dial_anywhere: anywhere,
        per_minute: Number(perMinute),
        per_day: Number(perDay),
        max_duration_s: Number(longest),
      });
      await onSaved();
    });
    if (done) setSaved("dialling");
  };

  return (
    <>
      <Card>
        <CardHead title="Limits" meta="Each world has its own. Leave a box empty for unlimited; type 0 to block it." />
        <div className="box-body">
          <Segmented
            options={WORLDS}
            value={env}
            onChange={(world) => {
              setEnv(world);
              setWanted(typedOf(org, world));
              setLends(org.quotas[world]?.lends ?? null);
              setSaved(null);
            }}
          />
        </div>
        <div className="box-limits">
          {QUOTAS.map((quota) => (
            <Field key={quota} label={ABOUT[quota].name}>
              <Input inputMode="numeric" value={wanted[quota] ?? ""} placeholder="unlimited" onChange={(event) => setWanted({ ...wanted, [quota]: digits(event.target.value) })} />
              <div className="box-limit-about">
                {ABOUT[quota].about}
                {HELD[quota] !== undefined && ` · holding ${org.holding[HELD[quota]]}`}
              </div>
            </Field>
          ))}
        </div>
        <div className="box-body">
          <Field label="The runtime's keys this org may use">
            <LendsPicker key={env} vendors={vendors.value ?? []} lends={lends} onChange={setLends} />
          </Field>
        </div>
        <div className="box-save">
          <Button kind="primary" size="md" disabled={quotas.busy} onClick={() => void saveLimits()}>
            {quotas.busy ? "Saving…" : "Save limits"}
          </Button>
          {saved === "quotas" && <span className="box-done">Saved. They bite the next call and the next register.</span>}
        </div>
        <Refused>{quotas.refused}</Refused>
      </Card>

      {guards !== null && (
        <Card>
          <CardHead title="Outgoing calls" meta="Limits on the calls this org's agents place" />
          <div className="box-anywhere">
            <span className="box-anywhere-words">
              <strong>Allow calls to any number</strong>
              <span className="ui-note">When off, agents can only call numbers that already called or wrote to this org.</span>
            </span>
            <Switch on={anywhere} onChange={setAnywhere} label="Allow calls to any number" />
          </div>
          <div className="box-limits">
            <Field label="Calls per minute">
              <Input inputMode="numeric" value={perMinute} onChange={(event) => setPerMinute(digits(event.target.value))} />
            </Field>
            <Field label="Calls per day">
              <Input inputMode="numeric" value={perDay} onChange={(event) => setPerDay(digits(event.target.value))} />
            </Field>
            <Field label="Longest call (seconds)">
              <Input inputMode="numeric" value={longest} onChange={(event) => setLongest(digits(event.target.value))} />
            </Field>
          </div>
          <div className="box-save">
            <Button kind="primary" size="md" disabled={dialling.busy} onClick={() => void saveGuards()}>
              {dialling.busy ? "Saving…" : "Save call limits"}
            </Button>
            {saved === "dialling" && <span className="box-done">Saved. They bite the next dial.</span>}
          </div>
          <Refused>{dialling.refused}</Refused>
        </Card>
      )}
    </>
  );
}
