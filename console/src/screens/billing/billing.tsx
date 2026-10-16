/** /billing: hands the signed-in person to the box's billing page, as themselves, in this org. */

import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { aLoginCode } from "@pinecall/core/login";
import { LimitsSchema } from "@pinecall/core/wire/rest-org";
import "./billing.css";

/**
 * The billing page sends anyone who arrives without a session here: the shell has already signed
 * them in, so a one-use login code carries them back, in the org they are working in, with the plan
 * they picked. The billing page is the box's own (`billing_url` of GET /v1/limits); none, nothing bills.
 */
export function BillingHop(): ReactNode {
  const credentials = useCredentials();
  const [params] = useSearchParams();
  const plan = params.get("plan");
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    const go = async (): Promise<void> => {
      const limits = LimitsSchema.parse(await read(credentials, "/v1/limits"));
      if (limits.billing_url === null) throw new Error(NO_BILLING);
      const there = new URL(limits.billing_url);
      there.searchParams.set("login", await aLoginCode(credentials));
      if (plan !== null) there.searchParams.set("plan", plan);
      if (!gone) window.location.replace(there.toString());
    };
    go().catch((failed: unknown) => {
      if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
    });
    return () => {
      gone = true;
    };
  }, [credentials, plan]);

  return (
    <div className="billing-hop">
      <div className="billing-hop-card">
        <img className="billing-hop-mark" src="/pinecall-mark.png" alt="" />
        <h1>{refused === null ? "Opening billing…" : "Billing did not open"}</h1>
        <p>{refused ?? "Taking you to your plan, signed in as you."}</p>
      </div>
    </div>
  );
}

const NO_BILLING = "This box does not bill: nothing to buy here.";
