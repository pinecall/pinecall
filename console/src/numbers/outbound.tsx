/** Calls the agents place: whether the org can dial out, from which numbers and within which limits, and the one step that makes it able to. */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { z } from "zod";

import { GatewayError, post, read, type Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Steps, useMove } from "./parts";
import { shown } from "./words";

const OutboundSchema = z.looseObject({
  ready: z.boolean(),
  from_numbers: z.array(z.string()),
  /** One sentence per thing missing. */
  steps_missing: z.array(z.string()),
  guards: z.looseObject({ dial_anywhere: z.boolean(), per_minute: z.number(), per_day: z.number(), max_duration_s: z.number() }),
});
type Outbound = z.infer<typeof OutboundSchema>;

const ProvisionedSchema = z.looseObject({ steps: z.array(z.string()), ready: z.boolean() });

/** Null where the org has no account to dial through, or the key may not ask. */
async function readOutbound(credentials: Credentials): Promise<Outbound | null> {
  try {
    return OutboundSchema.parse(await read(credentials, "/v1/carrier/outbound"));
  } catch (failed) {
    if (failed instanceof GatewayError && [403, 404, 405, 409].includes(failed.status)) return null;
    throw failed;
  }
}

/** Make the org's account dialable; `dryRun` answers what would be done and writes nothing. */
async function provision(credentials: Credentials, dryRun: boolean): Promise<z.infer<typeof ProvisionedSchema>> {
  return ProvisionedSchema.parse(await post(credentials, `/v1/carrier/outbound${dryRun ? "?dry_run=true" : ""}`, {}));
}

/** Draws nothing for an org with no account to call through. */
export function OutboundCard(): ReactNode {
  const credentials = useCredentials();
  const mover = useMove();
  const [outbound, setOutbound] = useState<Outbound | null>(null);
  const [plan, setPlan] = useState<string[] | null>(null);
  const reread = useCallback((): void => void readOutbound(credentials).then(setOutbound, () => undefined), [credentials]);
  useEffect(reread, [reread]);
  if (outbound === null) return null;
  const { guards } = outbound;
  return (
    <section className="dash-card num-card num-out" aria-label="Outbound calls">
      <div className="num-card-top">
        <span className="dash-eyebrow">Calls your agents place</span>
        <span className={outbound.ready ? "num-rings num-rings-good" : "num-rings num-rings-warn"}>{outbound.ready ? "Ready" : "Not set up"}</span>
      </div>
      {mover.refused !== null && (
        <p className="cfg-refused" role="alert">
          {mover.refused}
        </p>
      )}
      {outbound.ready ? (
        <p className="num-out-says">
          An agent can call out from {outbound.from_numbers.length === 0 ? "no number yet" : outbound.from_numbers.map(shown).join(", ")}: at most {guards.per_minute} calls a minute and {guards.per_day} a day, each up to {Math.round(guards.max_duration_s / 60)} minutes
          {guards.dial_anywhere ? "." : ", and only to numbers that called or wrote to you first, or that somebody verified as their own."}
        </p>
      ) : plan !== null ? (
        <>
          <span className="num-plan-title">What will happen. Nothing is changed until you confirm.</span>
          <Steps steps={plan} />
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" disabled={mover.busy} onClick={() => setPlan(null)}>
              Back
            </button>
            <button type="button" className="cfg-save" disabled={mover.busy} onClick={() => void mover.move(() => provision(credentials, false)).then(() => (setPlan(null), reread()), () => undefined)}>
              {mover.busy ? "Working…" : "Set it up"}
            </button>
          </div>
        </>
      ) : (
        <>
          <ul className="num-out-missing">
            {outbound.steps_missing.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
          <div>
            <button type="button" className="app-button" disabled={mover.busy} onClick={() => void mover.move(() => provision(credentials, true)).then((read) => setPlan(read.steps), () => undefined)}>
              {mover.busy ? "Checking…" : "See what setting it up does"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
