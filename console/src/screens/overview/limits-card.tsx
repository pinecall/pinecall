/** The org's limits in this world as what is used of each, when the monthly ones start again, and whose keys a call runs on. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import type { Limits } from "@pinecall/core/wire/rest-org";
import { useCredentials } from "@pinecall/core/credentials";
import { keysSaid, openBilling } from "../../lib/limits";
import { Card, CardHead, Stat, Stats } from "../../ui";
import { readVendors } from "../providers/door";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// The meters a new org asks about first; the rest are the Usage screen's.
const SHOWN: { name: "minutes" | "evals" | "simulations" | "numbers"; label: string; monthly: boolean }[] = [
  { name: "minutes", label: "Minutes", monthly: true },
  { name: "evals", label: "Evals", monthly: true },
  { name: "simulations", label: "Simulations", monthly: true },
  { name: "numbers", label: "Bought numbers", monthly: false },
];

/** The first of next month (UTC), as `1 Nov`: when minutes, evals and simulations start again. */
export function startsAgain(now: Date): string {
  return `1 ${MONTHS[(now.getUTCMonth() + 1) % 12]}`;
}

/** One meter as what is used of the limit, or what is used when there is none. */
export function usedOf(meter: { limit: number | null; used: number }): { value: string; of: string } {
  const used = String(Math.round(meter.used * 10) / 10);
  return meter.limit === null ? { value: used, of: "no limit" } : { value: used, of: `of ${meter.limit}` };
}

/** The card: four meters and the keys line; the vendors the org brought are read here, once. */
export function LimitsCard({ limits }: { limits: Limits }): ReactNode {
  const credentials = useCredentials();
  const [brought, setBrought] = useState<string[] | null>(null);
  const billing = limits.billing_url;

  useEffect(() => {
    let gone = false;
    readVendors(credentials).then(
      (vendors) => {
        if (!gone) setBrought(vendors);
      },
      () => {
        if (!gone) setBrought([]);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const next = startsAgain(new Date());
  const more =
    billing === null ? undefined : (
      <a
        className="ui-text-action"
        href={billing}
        onClick={(event) => {
          event.preventDefault();
          openBilling(billing, credentials);
        }}
      >
        Upgrade
      </a>
    );
  return (
    <Card>
      <CardHead title={`Limits in ${limits.world}`} meta={`minutes, evals and simulations start again ${next}`} action={more} />
      <div className="ovw-limits">
        <Stats min={150}>
          {SHOWN.map((one) => {
            const meter = usedOf(limits[one.name]);
            return <Stat key={one.name} size="small" label={one.label} value={meter.value} of={meter.of} />;
          })}
        </Stats>
        <div className="ovw-keys">
          {brought === null ? "Reading whose keys calls run on…" : keysSaid(brought, limits.lends)}
          <Link to="/providers" className="ovw-keys-link">
            Providers
          </Link>
        </div>
      </div>
    </Card>
  );
}
