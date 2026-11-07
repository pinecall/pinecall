/** Billing: hands the signed-in person to where the org pays, as themselves, in this org — from the sidebar's row, or back from that page. */

import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { aLoginCode } from "@pinecall/core/login";
import { LimitsSchema } from "@pinecall/core/wire/rest-org";
import "./billing.css";

/**
 * The runtime holds no plan: where the org buys one is the page it names (`billing_url` of GET
 * /v1/limits), and this screen is the door to it, signed in — a one-use login code carries the
 * person there, in the org they are working in. The same page sends anyone who arrives without a
 * session here, with the plan they picked, and the shell signs them in first. A runtime that names
 * no page draws no Billing row (lib/mode.ts), so this is reached only by a path typed by hand.
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
        <img className="billing-hop-mark" src="/pinecall-mark-b219dacb.png" alt="" />
        <h1>{refused === null ? "Opening billing…" : "Billing did not open"}</h1>
        <p>{refused ?? "Taking you to your plan, signed in as you."}</p>
      </div>
    </div>
  );
}

const NO_BILLING = "This box does not bill: nothing to buy here.";
