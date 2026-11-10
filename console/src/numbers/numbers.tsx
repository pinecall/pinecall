/** Numbers, the same page as Apps: the org's numbers in a list, and beside it the one open; a new one is added in the side panel. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, useNavigate, useParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { AddNumberPanel } from "./add-number";
import { readCarriers, readCatalog, readNumbers, type Carrier, type Catalog, type NumberRow } from "./door";
import { NumberView } from "./number-view";
import { OutboundCard } from "./outbound";
import { TestLine } from "./test-line";
import { RINGS, shown } from "./words";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "./numbers.css";

const HOME = "/numbers";

/** What the org's numbers are read with, shared by this page and an agent's Channels. */
export function useNumbers(): { rows: NumberRow[] | null; carriers: Carrier[]; catalog: Catalog | null; refused: string | null; reread: () => void } {
  const credentials = useCredentials();
  const [rows, setRows] = useState<NumberRow[] | null>(null);
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const reread = useCallback((): void => {
    readNumbers(credentials).then(
      (read) => (setRows(read.filter((one) => one.route.number !== null)), setRefused(null)),
      (failed: unknown) => (setRows((was) => was ?? []), setRefused(saidBy(failed))),
    );
    readCarriers(credentials).then(setCarriers, () => undefined);
  }, [credentials]);
  useEffect(() => {
    reread();
    readCatalog(credentials).then(setCatalog, () => undefined);
  }, [credentials, reread]);
  return { rows, carriers, catalog, refused, reread };
}

export function NumbersPage(): ReactNode {
  const navigate = useNavigate();
  const { number: asked } = useParams();
  const { agents } = useOrg();
  const slugs = useMemo(() => agents.map((one) => one.slug), [agents]);
  const { rows, carriers, catalog, refused, reread } = useNumbers();
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("");
  const stopAdding = useCallback(() => setAdding(false), []);

  const open = rows?.find((one) => one.route.number === asked);
  const wanted = filter.trim().toLowerCase();
  const shownRows = (rows ?? []).filter((one) => wanted === "" || `${one.route.number ?? ""} ${shown(one.route.number)} ${one.route.agent}`.toLowerCase().includes(wanted));

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  if (rows !== null && asked === undefined && rows[0]?.route.number != null) return <Navigate to={`${HOME}/${encodeURIComponent(rows[0].route.number)}`} replace />;
  if (rows !== null && asked !== undefined && open === undefined) return <Navigate to={HOME} replace />;

  const add = (
    <button type="button" className="app-button num-add" onClick={() => setAdding(true)}>
      <Icon name="plus" size={12} />
      Add
    </button>
  );

  return (
    <>
      <PageHead open={open === undefined ? undefined : shown(open.route.number)} />
      <div className="app-layout">
        <aside className="app-list" aria-label="Numbers">
          <div className="app-list-head">
            <span className="app-list-title">Numbers</span>
            <span className="dash-quiet">{rows === null ? "" : rows.length}</span>
            <span className="num-list-add">{add}</span>
          </div>
          <input className="app-input app-search" aria-label="Search numbers" placeholder="Search numbers" value={filter} onChange={(event) => setFilter(event.target.value)} />
          <div className="app-rows">
            {shownRows.map((one) => (
              <NavLink key={one.route.number} to={`${HOME}/${encodeURIComponent(one.route.number ?? "")}`} className={({ isActive }) => (isActive ? "app-row app-row-on" : "app-row")}>
                <span className="app-row-top">
                  <span className="dash-clip">{shown(one.route.number)}</span>
                  <span className={`app-dot app-dot-${RINGS[one.rings].mood}`} title={RINGS[one.rings].said} aria-hidden="true" />
                </span>
                <span className="app-row-under dash-clip">
                  {one.route.agent}
                  {one.route.channel === "whatsapp" ? " · WhatsApp" : ""}
                </span>
              </NavLink>
            ))}
            {rows !== null && rows.length > 0 && shownRows.length === 0 && <p className="dash-quiet app-none">Nothing by that number.</p>}
          </div>
        </aside>
        <div className="app-open">
          <div className="app-main">
            {refused !== null && <p className="app-refused">{refused}</p>}
            {rows === null && <p className="dash-quiet">Reading…</p>}
            {rows !== null && rows.length === 0 && (
              <div className="app-empty">
                <h2 className="app-name">No number in {WORLD} yet</h2>
                <p className="dash-quiet">A number is how a caller reaches an agent by phone or WhatsApp. Buy one here, bring one from Twilio or your own carrier, or connect WhatsApp.</p>
                <div>
                  <button type="button" className="cfg-save" onClick={() => setAdding(true)}>
                    Add a number
                  </button>
                </div>
              </div>
            )}
            {open !== undefined && <NumberView key={open.route.number} row={open} carriers={carriers} catalog={catalog} agents={slugs} onChanged={reread} onGone={() => (reread(), void navigate(HOME, { replace: true }))} />}
            {WORLD === "sandbox" && <TestLine agents={slugs} />}
            {rows !== null && rows.length > 0 && <OutboundCard />}
          </div>
        </div>
      </div>
      {adding && <AddNumberPanel agents={slugs} onAdded={reread} onClose={stopAdding} />}
    </>
  );
}
