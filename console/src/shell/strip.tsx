/** The strip over every screen while this world refuses: a quota used up this month, or a production closed to the org. */

import type { ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { openBilling } from "../lib/limits";
import { useOrg } from "../lib/org";
import { closedToTheOrg, stripSaid } from "../lib/used-up";

// The limits are read when the feed says a call ended or a quota refused (lib/limits.tsx), so the
// strip appears the moment a refusal lands and goes the moment the month starts again.
export function Strip(): ReactNode {
  const credentials = useCredentials();
  const { limits } = useOrg();
  if (limits === null) return null;
  const said = stripSaid(limits, new Date());
  if (said === null) return null;
  const billing = limits.billing_url;
  return (
    <div className="strip" role="status">
      <span className="strip-said">{said}</span>
      {billing !== null && (
        <a
          className="ui-text-action strip-action"
          href={billing}
          onClick={(event) => {
            event.preventDefault();
            openBilling(billing, credentials);
          }}
        >
          {closedToTheOrg(limits) ? "Choose a plan" : "Upgrade"}
        </a>
      )}
    </div>
  );
}
