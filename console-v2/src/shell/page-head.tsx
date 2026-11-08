/** The header a page chooses to wear: where it is, down to the one thing open, and the buttons that page adds. */

import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";

import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Icon } from "./icons";
import { rowOfPage } from "./menu";

export function PageHead({ open, children }: { open?: string | undefined; children?: ReactNode }): ReactNode {
  const { whose, orgs } = useOrg();
  const { pathname } = useLocation();
  const row = rowOfPage(pathname);
  const here = orgs?.find((one) => one.here);
  const org = here?.name ?? here?.slug ?? whose?.slug ?? whose?.org ?? "";
  return (
    <header className="sh-head">
      {WORLD === "sandbox" && (
        <span className="sh-in-sandbox">
          <Icon name="cases" size={13} />
          Sandbox
        </span>
      )}
      <h1 className="sh-crumbs">
        <Link to="/" className="sh-crumb">
          {org}
        </Link>
        <span className="sh-crumb-gap">/</span>
        {row !== undefined && <Icon name={row.icon} size={15} />}
        {open === undefined ? (
          <span className="sh-title">{row?.name ?? "Not found"}</span>
        ) : (
          <>
            <span className="sh-crumb">{row?.name}</span>
            <span className="sh-crumb-gap">/</span>
            <span className="sh-title">{open}</span>
          </>
        )}
      </h1>
      <span className="sh-fill" />
      {children}
    </header>
  );
}
