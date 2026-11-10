/** The frame of every page: the sidebar with the organization, the world and the one menu; a header is each page's own. */

import { useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { useOrg } from "../lib/org";
import { inWorld, pageHere, WORLD, type World } from "../lib/world";
import { useFirstAgent } from "../apps/first-agent";
import { NoProduction } from "../login";
import { BrandMark, useBrand, wornBy } from "../login/way-in";
import { SIDE_SLOT } from "../ui/side-panel";
import { Icon } from "./icons";
import { Me } from "./me";
import { MENU, OPERATOR_MENU, rowOfPage } from "./menu";
import { OrgPicker } from "./org-picker";
import { PageHead } from "./page-head";
import "./shell.css";

const WORLDS: readonly { world: World; name: string }[] = [
  { world: "production", name: "Production" },
  { world: "sandbox", name: "Sandbox" },
];

function WorldSwitch(): ReactNode {
  const { whose } = useOrg();
  return (
    <div className="sh-worlds" role="group" aria-label="World">
      {WORLDS.map(({ world, name }) => {
        const barred = world === "production" && whose !== null && !whose.production;
        return (
          <button
            key={world}
            type="button"
            aria-pressed={world === WORLD}
            className={world === WORLD ? "sh-world sh-world-on" : "sh-world"}
            disabled={barred}
            title={barred ? "Your organization has not let you into production" : undefined}
            onClick={() => world !== WORLD && window.location.assign(inWorld(world, pageHere()))}
          >
            <span className={`sh-dot sh-dot-${world === WORLD ? world : "off"}`} aria-hidden="true" />
            {name}
          </button>
        );
      })}
    </div>
  );
}

const FOLDED_UNDER = "pinecall.side-folded";

// A convenience of this browser: without storage the sidebar just opens unfolded.
function useFolded(): [boolean, () => void] {
  const [folded, setFolded] = useState(() => {
    try {
      return window.localStorage.getItem(FOLDED_UNDER) === "1";
    } catch {
      return false;
    }
  });
  const flip = (): void => {
    try {
      window.localStorage.setItem(FOLDED_UNDER, folded ? "0" : "1");
    } catch {
      // Lasts only for the page.
    }
    setFolded(!folded);
  };
  return [folded, flip];
}

function Sidebar({ folded, onFold, onLeave }: { folded: boolean; onFold: () => void; onLeave: () => void }): ReactNode {
  const { live, operator } = useOrg();
  const brand = useBrand();
  return (
    <nav className="sh-side" aria-label="Console">
      <div className="sh-top">
        <Link to="/" className="sh-logo login-brand" style={brand === null ? undefined : wornBy(brand)} aria-label="Dashboard">
          {brand !== null && <BrandMark brand={brand} small={folded} />}
        </Link>
        <OrgPicker />
      </div>
      <hr className="sh-rule" />
      <div className="sh-place">
        <WorldSwitch />
      </div>
      <div className="sh-menu">
        {(operator === true ? [...MENU, OPERATOR_MENU] : MENU).map((group) => (
          <div key={group.title ?? "main"} className="sh-group">
            {group.title !== null && <span className="sh-group-title">{group.title}</span>}
            {group.rows.map((row) => (
              <NavLink key={row.path} to={row.path} end={row.path === "/"} title={folded ? row.name : undefined} className={({ isActive }) => (isActive ? "sh-row sh-row-on" : "sh-row")}>
                <Icon name={row.icon} size={16} />
                <span className="sh-row-name">{row.name}</span>
                {row.path === "/calls" && live.length > 0 && <span className="sh-live">{live.length} live</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </div>
      <div className="sh-me">
        <Me onLeave={onLeave} />
        <NavLink to="/notifications" className="sh-icon" aria-label="Notifications" title="Notifications">
          <Icon name="bell" size={15} />
        </NavLink>
        <button type="button" className="sh-icon" aria-label={folded ? "Open the sidebar" : "Fold the sidebar"} title={folded ? "Open the sidebar" : "Fold the sidebar"} onClick={onFold}>
          <Icon name="panel" size={15} />
        </button>
      </div>
    </nav>
  );
}

export function Shell({ onLeave }: { onLeave: () => void }): ReactNode {
  const { whose } = useOrg();
  const [folded, onFold] = useFolded();
  useFirstAgent();
  // A person may hold a key and not production: the page says so, and opens the sandbox.
  if (WORLD === "production" && whose !== null && !whose.production) return <NoProduction said="Your organization has not let you into production yet." />;
  return (
    <div className={folded ? "sh-frame sh-frame-folded" : "sh-frame"}>
      <Sidebar folded={folded} onFold={onFold} onLeave={onLeave} />
      <div className="sh-page">
        <div className="sh-body">
          <Outlet />
        </div>
      </div>
      <aside id={SIDE_SLOT} className="sh-aside" />
    </div>
  );
}

/** A row of the menu whose page is the next to be designed. */
export function NotYet(): ReactNode {
  const { pathname } = useLocation();
  const name = rowOfPage(pathname)?.name ?? "This page";
  return (
    <>
      <PageHead />
      <p className="sh-notyet">{name} is not built yet. Console v2 goes page by page.</p>
    </>
  );
}
