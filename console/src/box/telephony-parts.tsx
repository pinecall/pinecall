/** What the operator's telephony pages share: the page that only an operator reads, a section's head, an org's link, a door read with its refusal, and a number's words. */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useOrg } from "../lib/org";
import { Icon, type IconName } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import type { BoxNumber } from "./telephony-door";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "../numbers/numbers.css";
import "../test/test.css";
import "./telephony.css";

/** The page's header, then its content for an operator alone: anybody else reads one line, and nothing is fetched. */
export function OperatorPage({ children }: { children: ReactNode }): ReactNode {
  const { whose } = useOrg();
  return (
    <>
      <PageHead />
      <div className="tst tel">
        {whose === null && <p className="dash-quiet">Reading…</p>}
        {whose !== null && whose.operator !== true && <p className="dash-quiet tel-calm">This page belongs to the operator, the person who runs this deployment. Nothing was read.</p>}
        {whose?.operator === true && children}
      </div>
    </>
  );
}

export function Head({ icon, title, about, children }: { icon: IconName; title: string; about: string; children?: ReactNode }): ReactNode {
  return (
    <header className="tst-head">
      <span className="tst-head-mark" aria-hidden="true">
        <Icon name={icon} size={16} />
      </span>
      <span className="tst-head-words">
        <span className="tst-head-title">{title}</span>
        <span className="tst-head-about">{about}</span>
      </span>
      {children}
    </header>
  );
}

/** An org by its slug, opening its page among the operator's organizations. */
export function OrgLink({ slug, name }: { slug: string; name?: string | undefined }): ReactNode {
  return (
    <Link to={`/box/orgs/${encodeURIComponent(slug)}`} className="tel-org">
      {name ?? slug}
    </Link>
  );
}

export interface Door<Value> {
  /** Null until the door has answered. */
  value: Value | null;
  refused: string | null;
  reread: () => void;
}

/** A door read when the page opens and again when asked; `ask` must be stable. */
export function useDoor<Value>(ask: () => Promise<Value>): Door<Value> {
  const [value, setValue] = useState<Value | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const reread = useCallback((): void => {
    ask().then(
      (read) => (setValue(read), setRefused(null)),
      (failed: unknown) => setRefused(saidBy(failed)),
    );
  }, [ask]);
  useEffect(reread, [reread]);
  return { value, refused, reread };
}

const CAME_IN: Record<string, string> = {
  bought: "Bought on the deployment's account",
  twilio: "Imported from the org's Twilio",
  sip: "Comes from the org's own PBX",
  whatsapp: "The org's WhatsApp",
  imported: "Imported from an account since removed",
  hooked: "Pointed here by the org, from its own carrier",
  typed: "Added by hand by an operator",
};

/** How a number reached the deployment; a way the gateway adds later reads as itself. */
export function cameIn(row: BoxNumber): string {
  return CAME_IN[row.came_in] ?? row.came_in;
}

export interface Rings {
  mood: "held" | "broke" | "waiting";
  said: string;
  /** What that means, in a sentence. */
  why: string;
}

/** What a call to the number does now. */
export function ringsOf(row: BoxNumber): Rings {
  if (!row.approved) return { mood: "waiting", said: "Needs approval", why: "No call to it opens until an operator approves it." };
  if (!row.running) return { mood: "broke", said: "Not answered", why: `Nothing is running ${row.agent} in ${row.env}, so a call rings out.` };
  return { mood: "held", said: "Answered", why: `${row.agent} picks up.` };
}
