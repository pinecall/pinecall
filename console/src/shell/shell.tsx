/** The frame of every page: the sidebar with the organization, the world and the one menu; a header is each page's own. On a phone the sidebar is a drawer and a bar of tabs sits at the foot. */

import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { useOrg } from "../lib/org";
import { usePhone } from "../lib/phone";
import { inWorld, pageHere, WORLD, type World } from "../lib/world";
import { useFirstAgent } from "../apps/first-agent";
import { NoProduction } from "../login";
import { BrandMark, useBrand, wornBy } from "../login/way-in";
import { SIDE_SLOT } from "../ui/side-panel";
import { Icon } from "./icons";
import { Me } from "./me";
import { MENU, OPERATOR_MENU, rowOfPage, TABS } from "./menu";
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

// `onPick` hears every link followed in it: a phone's drawer shuts on it, even onto the page already open.
function Sidebar({ folded, onFold, onLeave, onPick }: { folded: boolean; onFold: () => void; onLeave: () => void; onPick: () => void }): ReactNode {
  const { live, operator } = useOrg();
  const brand = useBrand();
  return (
    <nav className="sh-side" aria-label="Console" onClick={(event) => event.target instanceof Element && event.target.closest("a") !== null && onPick()}>
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
        <button type="button" className="sh-icon sh-fold" aria-label={folded ? "Open the sidebar" : "Fold the sidebar"} title={folded ? "Open the sidebar" : "Fold the sidebar"} onClick={onFold}>
          <Icon name="panel" size={15} />
        </button>
      </div>
    </nav>
  );
}

/** A phone's foot: the pages most opened away from a desk, and the whole menu behind the last tab. */
function TabBar({ drawer, onMenu }: { drawer: boolean; onMenu: () => void }): ReactNode {
  const { live } = useOrg();
  const { pathname } = useLocation();
  const here = rowOfPage(pathname)?.path;
  const onATab = TABS.some((tab) => tab.path === here);
  return (
    <nav className="sh-tabs" aria-label="Most used">
      {TABS.map((tab) => (
        <NavLink key={tab.path} to={tab.path} end={tab.path === "/"} className={({ isActive }) => (isActive && !drawer ? "sh-tab sh-tab-on" : "sh-tab")}>
          <Icon name={tab.icon} size={20} />
          <span>{tab.name}</span>
          {tab.path === "/calls" && live.length > 0 && <span className="sh-tab-count">{live.length}</span>}
        </NavLink>
      ))}
      <button type="button" className={drawer || !onATab ? "sh-tab sh-tab-on" : "sh-tab"} aria-expanded={drawer} onClick={onMenu}>
        <Icon name="menu" size={20} />
        <span>Menu</span>
      </button>
    </nav>
  );
}

/** The drawer of a phone: open from the tab bar, shut by any page opened, a tap beside it or Escape. */
function useDrawer(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return [open, setOpen];
}

export function Shell({ onLeave }: { onLeave: () => void }): ReactNode {
  const { whose } = useOrg();
  const [folded, onFold] = useFolded();
  const phone = usePhone();
  const [drawer, setDrawer] = useDrawer();
  useFirstAgent();
  // A person may hold a key and not production: the page says so, and opens the sandbox.
  if (WORLD === "production" && whose !== null && !whose.production) return <NoProduction said="Your organization has not let you into production yet." />;
  // A phone has no room to fold: its sidebar is the drawer, whole.
  const narrow = folded && !phone;
  const frame = ["sh-frame", narrow ? "sh-frame-folded" : "", phone && drawer ? "sh-frame-drawer" : ""].filter(Boolean).join(" ");
  return (
    <div className={frame}>
      <Sidebar folded={narrow} onFold={onFold} onLeave={onLeave} onPick={() => setDrawer(false)} />
      {phone && drawer && <button type="button" className="sh-scrim" aria-label="Close the menu" onClick={() => setDrawer(false)} />}
      <div className="sh-page">
        <div className="sh-body">
          <Outlet />
        </div>
      </div>
      <aside id={SIDE_SLOT} className="sh-aside" />
      {phone && <TabBar drawer={drawer} onMenu={() => setDrawer(!drawer)} />}
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
