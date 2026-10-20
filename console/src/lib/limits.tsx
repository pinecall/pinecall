/** Org limits hook (GET /v1/limits) and the minutes meter. */

import { useState, type ReactNode } from "react";

import { type Limits, LimitsSchema } from "@pinecall/core/wire/rest-org";
import { type Credentials, GatewayError, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { aLoginCode } from "@pinecall/core/login";
import { Stat } from "../ui";

// The minutes and the spend a limit counts are what a call that ended or was summarised added.
const WHAT_USES_A_LIMIT = ["call.ended", "call.summary"] as const;

/** Read limits on open and when the feed says a call used some; null until loaded, or on 404. */
export function useLimits(): Limits | null {
  const credentials = useCredentials();
  const [limits, setLimits] = useState<Limits | null>(null);

  useFed(
    () => {
      read(credentials, "/v1/limits").then(
        (answered) => setLimits(LimitsSchema.parse(answered)),
        (refused: unknown) => {
          // Older gateway without the door.
          if (refused instanceof GatewayError && refused.status === 404) setLimits(null);
        },
      );
    },
    { types: WHAT_USES_A_LIMIT },
  );

  return limits;
}

/** Minutes used against the org's limit, and the billing URL if any. */
export interface MinutesMeter {
  used: number;
  limit: number;
  billing: string | null;
}

export function minutesMeter(limits: Limits | null): MinutesMeter | null {
  if (limits === null || limits.minutes.limit === null) return null;
  return { used: Math.min(limits.minutes.used, limits.minutes.limit), limit: limits.minutes.limit, billing: limits.billing_url };
}

/**
 * The billing page in a new tab, signed in as this person: the tab opens at once (a tab opened after
 * an await is a popup the browser blocks), then goes to the page with a one-use login code; if
 * minting fails the page's own sign-in asks.
 */
export function openBilling(billing: string, credentials: Credentials): void {
  const tab = window.open("about:blank", "_blank");
  const go = (code: string | null): void => {
    const there = new URL(billing);
    if (code !== null) there.searchParams.set("login", code);
    if (tab === null) window.location.assign(there.toString());
    else tab.location.href = there.toString();
  };
  aLoginCode(credentials).then(go, () => go(null));
}

/** Minutes meter; shows "Upgrade" only when the box has a billing URL. */
export function Minutes({ meter, size }: { meter: MinutesMeter; size: "big" | "small" }): ReactNode {
  const credentials = useCredentials();
  const billing = meter.billing;
  const upgrade = billing === null ? null : (
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
  const of = (
    <>
      of {meter.limit}
      {upgrade !== null && <> · {upgrade}</>}
    </>
  );
  const used = Math.round(meter.used * 10) / 10;
  return size === "big" ? (
    <Stat size="big" label="Minutes used" value={used} delta={of} tone="flat" />
  ) : (
    <Stat size="small" label="Minutes used" value={used} of={of} accent />
  );
}

/** What the runtime lends this org of one vendor: every model, some named models, or nothing. */
export type Lending = "all" | "some" | "none";

/** Whether a call may run on the runtime's key for this vendor: `lends` null lends every key it holds. */
export function lending(lends: string[] | null, vendor: string): Lending {
  if (lends === null || lends.includes(vendor)) return "all";
  return lends.some((entry) => entry.startsWith(`${vendor}/`)) ? "some" : "none";
}

/** Whose keys a call runs on, in one line: the org's own, then what the runtime lends it. */
export function keysSaid(brought: string[], lends: string[] | null): string {
  const yours = brought.length === 0 ? "Yours: none" : `Yours: ${[...brought].sort().join(", ")}`;
  if (lends === null) return `${yours} · lent by the runtime: every vendor it holds a key for`;
  if (lends.length === 0) return `${yours} · lent by the runtime: none, bring a key for every vendor`;
  return `${yours} · lent by the runtime: ${lends.join(", ")}`;
}
