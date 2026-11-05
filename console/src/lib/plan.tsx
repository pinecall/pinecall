/** Whether production is open to the org, and the card a closed production shows in place of a screen that needs it. */

import { useEffect, useState, type ReactNode } from "react";

import { type Limits, LimitsSchema } from "@pinecall/core/wire/rest-org";
import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { inTheWorld } from "./mode";
import { openBilling } from "./limits";
import { Button, Card } from "../ui";

/** Production's limits as this person reads them; null while unread, or on a key production refuses. */
export function useProductionLimits(): Limits | null {
  const credentials = useCredentials();
  const [limits, setLimits] = useState<Limits | null>(null);
  useEffect(() => {
    let gone = false;
    read({ ...credentials, world: "production" }, "/v1/limits").then(
      (answered) => {
        if (!gone) setLimits(LimitsSchema.parse(answered));
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);
  return limits;
}

/** Production is closed to the org: no minutes and no messages — the free plan, which is the sandbox. */
export function productionClosed(limits: Limits | null): boolean {
  return limits !== null && limits.minutes.limit === 0 && limits.messages.limit === 0;
}

/** The card a production screen shows when production is closed, in place of a form every door would refuse. */
export function PlanWall({ limits, doing }: { limits: Limits; doing: string }): ReactNode {
  const credentials = useCredentials();
  const billing = limits.billing_url;
  return (
    <Card pad style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 640 }}>
      <strong>Production opens with a plan</strong>
      <span className="ui-note">
        Your free plan is the sandbox: build and test there, with minutes on our models. {doing} happens in production, where your customers call, and that opens when you
        choose a plan.
      </span>
      <span style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {billing !== null && (
          <Button kind="primary" size="md" onClick={() => openBilling(billing, credentials)}>
            Choose a plan
          </Button>
        )}
        <a className="ui-button ui-button-md" href={inTheWorld("sandbox", "/")}>
          Back to the sandbox
        </a>
      </span>
    </Card>
  );
}
