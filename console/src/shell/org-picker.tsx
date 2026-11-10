/** The organization this console is looking at, and the way to another of the person's. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { initialsOf } from "@pinecall/core/initials";
import { loginToOrg, type OrgOf } from "@pinecall/core/login";
import { orgOf } from "@pinecall/core/whoami";
import { keepKey } from "../lib/key";
import { useOrg } from "../lib/org";
import { inWorld, WORLD } from "../lib/world";
import { Icon } from "./icons";

// The list arrives after the page does: what the last answer said keeps the chevron from blinking in.
const MANY_UNDER = "pinecall-console-many-orgs";

function rememberedMany(): boolean {
  try {
    return window.localStorage.getItem(MANY_UNDER) === "1";
  } catch {
    return false;
  }
}

function nameOf(org: OrgOf): string {
  return org.name ?? org.slug ?? org.org;
}

export function OrgPicker(): ReactNode {
  const credentials = useCredentials();
  const { whose, orgs } = useOrg();
  const [open, setOpen] = useState(false);
  const [moving, setMoving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const held = useRef<HTMLDivElement>(null);
  const [remembered] = useState(rememberedMany);
  const many = orgs === null ? remembered : orgs.length > 1;

  useEffect(() => {
    if (orgs === null) return;
    try {
      window.localStorage.setItem(MANY_UNDER, orgs.length > 1 ? "1" : "0");
    } catch {
      // Without storage the chevron just arrives with the list.
    }
  }, [orgs]);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent): void => {
      if (!held.current?.contains(event.target as Node)) setOpen(false);
    };
    const escaped = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escaped);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escaped);
    };
  }, [open]);

  // A key belongs to one org: another's is minted, and the page starts over there.
  const moveTo = async (org: OrgOf): Promise<void> => {
    setMoving(true);
    setRefused(null);
    try {
      const signed = await loginToOrg(credentials, org.org);
      await keepKey(signed.key);
      window.location.assign(inWorld(WORLD, "/"));
    } catch (failed) {
      setRefused(saidBy(failed));
      setMoving(false);
    }
  };

  // Nothing to choose from: one organization needs no picker.
  if (!many) return null;

  const list = orgs ?? [];
  const here = list.find((one) => one.here);
  const groups = [
    { label: "Your organizations", rows: list.filter((one) => one.member !== false) },
    { label: "As operator", rows: list.filter((one) => one.member === false) },
  ].filter((group) => group.rows.length > 0);
  const name = here === undefined ? (whose === null ? "…" : orgOf(whose)) : nameOf(here);
  return (
    <div className="sh-org" ref={held}>
      <button type="button" className="sh-icon" title={name} aria-label={`Organization: ${name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="chevron" size={14} />
      </button>
      {open && (
        <div className="sh-org-menu" role="menu" aria-label="Organizations">
          <div className="sh-org-list">
            {groups.map((group) => (
              <div key={group.label} className="sh-org-group" role="group" aria-label={group.label}>
                <span className="sh-org-label">{group.label}</span>
                {group.rows.map((org) => (
                  <button key={org.org} type="button" role="menuitemradio" aria-checked={org.here} className={org.here ? "sh-org-pick sh-org-pick-on" : "sh-org-pick"} disabled={moving} onClick={() => (org.here ? setOpen(false) : void moveTo(org))}>
                    <span className="sh-org-mark sh-org-mark-small">{initialsOf(nameOf(org)).slice(0, 1)}</span>
                    <span className="sh-org-pick-name" title={nameOf(org)}>
                      {nameOf(org)}
                    </span>
                    {org.here ? <Icon name="check" size={14} /> : org.member !== false && <span className="sh-org-pick-role">{org.role}</span>}
                  </button>
                ))}
              </div>
            ))}
          </div>
          {orgs === null && <span className="sh-org-reading">Reading your organizations…</span>}
          {refused !== null && <span className="sh-org-refused">{refused}</span>}
        </div>
      )}
    </div>
  );
}
