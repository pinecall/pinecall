/** The header a page chooses to wear: where it is, down to the one thing open, and the buttons that page adds; on a phone, the way back to the list. */

import type { ReactNode } from "react";
import { Link, useLocation, type To } from "react-router";

import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Icon } from "./icons";
import { rowOfPage } from "./menu";

/** `back` is where a phone's back arrow goes from the one thing open: the menu row's page unless a page keeps its filters. */
export function PageHead({ open, mark, back, children }: { open?: string | undefined; mark?: ReactNode; back?: To | undefined; children?: ReactNode }): ReactNode {
  const { whose, orgs } = useOrg();
  const { pathname } = useLocation();
  const row = rowOfPage(pathname);
  const here = orgs?.find((one) => one.here);
  const org = here?.name ?? here?.slug ?? whose?.slug ?? whose?.org ?? "";
  return (
    <header className="sh-head" data-open={open === undefined ? undefined : ""}>
      {WORLD === "sandbox" && (
        <span className="sh-in-sandbox">
          <Icon name="cases" size={13} />
          Sandbox
        </span>
      )}
      {open !== undefined && row !== undefined && (
        <Link to={back ?? row.path} className="sh-back" aria-label={`Back to ${row.name}`}>
          <Icon name="back" size={20} />
        </Link>
      )}
      <h1 className="sh-crumbs">
        <Link to="/" className="sh-crumb sh-crumb-org">
          {org}
        </Link>
        <span className="sh-crumb-gap">/</span>
        {row !== undefined && (
          <span className="sh-crumb-icon">
            <Icon name={row.icon} size={15} />
          </span>
        )}
        {open === undefined ? (
          <span className="sh-title">{row?.name ?? "Not found"}</span>
        ) : (
          <>
            <span className="sh-crumb sh-crumb-row">{row?.name}</span>
            <span className="sh-crumb-gap sh-crumb-row">/</span>
            {mark}
            <span className="sh-title">{open}</span>
          </>
        )}
      </h1>
      <span className="sh-fill" />
      {children}
    </header>
  );
}
