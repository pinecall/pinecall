/** The sidebar: the org and its world, who is in view, what is looked at, what builds the agent in view, the harness, the workspace, and who is signed in, their own screens a click on their name. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { opens } from "@pinecall/core/scopes";
import { wantsAPerson } from "@pinecall/core/calls";
import { AGENT_SCREENS, BOX_SCREENS, inTheOtherWorld, ORG_SCREENS, rowOf, rowsOf, screenAt, tabsOf, WORLD, type Screen } from "../lib/mode";
import { useOrg } from "../lib/org";
import { orgOf, useScopes, useWhoami } from "../lib/whoami";
import { useWorld } from "../lib/world";
import { Icon, initialsOf } from "../ui";
import { Viewing } from "./viewing";

/** Whether the screen at this path is the row itself or one of its tabs — what lights the row. */
function onRowAt(path: string, table: readonly Screen[], row: Screen): boolean {
  const at = screenAt(path);
  return at !== undefined && table.includes(at) && rowOf(table, at).key === row.key;
}

export function Sidebar({ agent, onSearch }: { agent: string; onSearch: () => void }): ReactNode {
  const [folded, setFolded] = useState(false);
  const scopes = useScopes();
  const whose = useWhoami();
  const { live, here, operator } = useOrg();
  const { pathname } = useLocation();
  const open = (screen: Screen): boolean => scopes === null || opens(scopes, screen.key);
  const person = whose?.name ?? whose?.label ?? "";
  const role = here?.role ?? (whose === null ? "" : whose.subject === null || whose.subject === undefined ? "a machine's key" : "");

  // The agent in view decides whose rows are drawn; the workspace is the org's whoever is.
  const table = agent === "" ? ORG_SCREENS : AGENT_SCREENS;
  const prefix = agent === "" ? "" : `/a/${encodeURIComponent(agent)}`;
  const onAir = agent === "" ? live : live.filter((line) => line.agent === agent);
  const asking = onAir.some(wantsAPerson);

  // A row lands on itself, or — a row that is only a place for its tabs — on the first tab this
  // key opens. A row none of whose tabs open is not drawn: a link to nothing is a 403 on a click.
  const landing = (from: readonly Screen[], row: Screen, base: string): string | null => {
    const first = tabsOf(from, row).filter(open)[0];
    return first === undefined ? null : `${base}/${first.path}`;
  };
  const link = (from: readonly Screen[], row: Screen, base: string): ReactNode => {
    const to = landing(from, row, base);
    if (to === null) return null;
    const on = onRowAt(pathname, from, row);
    return (
      <NavLink key={row.key} to={to} end={row.path === ""} title={row.name} className={on ? "side-link side-link-on" : "side-link"}>
        <span className="side-icon">{row.icon !== undefined && <Icon name={row.icon} size={16} />}</span>
        <span className="side-name">{row.name}</span>
        {row.key === "calls" && onAir.length > 0 && (
          <span className={asking ? "side-badge side-badge-asking" : "side-badge"} title={asking ? "a caller wants a person" : undefined}>
            {onAir.length} live
          </span>
        )}
      </NavLink>
    );
  };

  const rows = rowsOf(table);
  const looked = rows.filter((row) => row.group === undefined);
  const built = rows.filter((row) => row.group === "build");
  const harness = rows.filter((row) => row.group === "harness");
  const workspace = rowsOf(ORG_SCREENS).filter((row) => row.group === "workspace");
  const yours = rowsOf(ORG_SCREENS).filter((row) => row.group === "yours" && open(row))[0];
  const box = rowsOf(BOX_SCREENS, WORLD, operator === true);
  const who = (
    <>
      <span className="side-user-avatar">{initialsOf(person || (whose === null ? "?" : orgOf(whose)))}</span>
      <span className="side-words">
        <span className="side-user-name">{person || "—"}</span>
        <span className="side-user-role">{capitalised(role)}</span>
      </span>
    </>
  );

  return (
    <aside className={folded ? "side side-folded" : "side"} aria-label="Screens">
      <div className="side-top">
        <Workspace />
        <Worlds />
        <Viewing agent={agent} />
      </div>

      <div className="side-scroll">
      <nav className="side-nav">
        <button type="button" className="side-link side-search" onClick={onSearch} title="Search">
          <span className="side-icon">
            <Icon name="search" size={16} />
          </span>
          <span className="side-name">Search</span>
          <span className="side-kbd">⌘K</span>
        </button>
        {looked.map((row) => link(table, row, prefix))}
        {built.length > 0 && (
          <>
            <div className="side-group">Build</div>
            {built.map((row) => link(table, row, prefix))}
          </>
        )}
        {harness.length > 0 && (
          <>
            <div className="side-group">Harness</div>
            {harness.map((row) => link(table, row, prefix))}
          </>
        )}
      </nav>

      <nav className="side-nav side-nav-foot">
        <div className="side-group">Workspace</div>
        {workspace.map((row) => link(ORG_SCREENS, row, ""))}
        {box.length > 0 && (
          <>
            <div className="side-group">Box</div>
            {box.map((row) => (
              <NavLink key={row.key} to={`/${row.path}`} title={row.name} className={({ isActive }) => (isActive ? "side-link side-link-on" : "side-link")}>
                <span className="side-icon">{row.icon !== undefined && <Icon name={row.icon} size={16} />}</span>
                <span className="side-name">{row.name}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>
      </div>

      <div className="side-foot">
        {yours === undefined ? (
          <div className="side-user" title={whose === null ? person : `${person} · key ${whose.key_id}`}>
            {who}
          </div>
        ) : (
          <NavLink to={`/${yours.path}`} title={`${yours.name}: what you are told, on every device of yours`} className={({ isActive }) => (isActive ? "side-user side-user-link side-user-on" : "side-user side-user-link")}>
            {who}
            <span className="side-user-bell">
              <Icon name="bell" size={15} />
            </span>
          </NavLink>
        )}
        <button type="button" className="side-fold" onClick={() => setFolded(!folded)} title={folded ? "Open the sidebar" : "Collapse the sidebar"}>
          <Icon name="panel" size={15} />
        </button>
      </div>
    </aside>
  );
}

function capitalised(word: string): string {
  return word === "" ? "" : word.charAt(0).toUpperCase() + word.slice(1);
}

/**
 * The two worlds as two halves of one control: the other one is the same screen with `/sandbox`
 * put on or taken off, at the same origin, on the same key — the browser's own path, not the
 * router's, which has this world's base stripped off.
 */
function Worlds(): ReactNode {
  const { world } = useWorld();
  const cross = (): void => window.location.assign(inTheOtherWorld(window.location.pathname));
  return (
    <div className="side-worlds" role="group" aria-label="world">
      {(["production", "sandbox"] as const).map((one) => (
        <button key={one} type="button" className={world === one ? `side-world side-world-on side-world-${one}` : "side-world"} aria-pressed={world === one} onClick={world === one ? undefined : cross}>
          <span className="side-world-dot" aria-hidden />
          {one === "production" ? "Production" : "Sandbox"}
        </button>
      ))}
    </div>
  );
}

/** The org this console is in and — when the person belongs to more than one — the move to another. */
function Workspace(): ReactNode {
  const whose = useWhoami();
  const { orgs } = useOrg();
  const { moveTo } = useWorld();
  const [open, setOpen] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const path = useLocation().pathname;

  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent): void => {
      if (box.current !== null && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const org = whose === null ? "" : orgOf(whose);
  // Another org is another key, minted for the same person (POST /v1/login/org) on either console:
  // a person of two orgs writes agents for both.
  const canMove = orgs !== null && orgs.length > 1;

  const move = async (target: string): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      await moveTo(target);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      setBusy(false);
    }
  };

  return (
    <div ref={box} className="side-org-wrap">
      <button type="button" className="side-org" onClick={() => canMove && setOpen(!open)} title={org} aria-expanded={open} disabled={!canMove}>
        <span className="side-tile">{initialsOf(org || "?").slice(0, 1)}</span>
        <span className="side-org-name">
          {org || "…"}
          {whose?.visiting === true && <span className="side-org-visit"> · as operator</span>}
        </span>
        {canMove && (
          <span className="side-caret">
            <Icon name="chevrons" size={13} />
          </span>
        )}
      </button>
      {open && orgs !== null && (
        <div className="side-orgs" role="menu">
          {[
            { label: "Your organizations", rows: orgs.filter((one) => one.member !== false) },
            { label: "Every other org on this box · as operator", rows: orgs.filter((one) => one.member === false) },
          ]
            .filter((group) => group.rows.length > 0)
            .map((group) => (
              <div key={group.label}>
                <div className="side-orgs-label">{group.label}</div>
                {group.rows.map((one) => (
                  <button key={one.org} type="button" className="side-orgs-row" disabled={busy || one.here} onClick={() => void move(one.org)}>
                    <span className="side-tile">{initialsOf(one.slug ?? one.name ?? one.org).slice(0, 1)}</span>
                    <span className="ui-clip">{one.slug ?? one.name ?? one.org}</span>
                    <span className="side-orgs-role">{one.here ? "here" : one.role}</span>
                  </button>
                ))}
              </div>
            ))}
          {refused !== null && <div className="ui-refused side-orgs-refused">{refused}</div>}
        </div>
      )}
    </div>
  );
}
