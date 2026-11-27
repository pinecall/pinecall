/** Numbers, Mailboxes, Messenger & Instagram, the same page as Apps: the org's numbers, its mailboxes or its Pages, in a list, and beside it the one open; a new one is added in the side panel. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, useNavigate, useParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { usePhone } from "../lib/phone";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { AddNumberPanel } from "./add-number";
import { readCarriers, readCatalog, readNumbers, type Carrier, type Catalog, type NumberRow } from "./door";
import { NumberView } from "./number-view";
import { OutboundCard } from "./outbound";
import { TestLine } from "./test-line";
import { addressSaid, CHANNEL_NAMES, ON_A_PAGE, RINGS, ringsSaid } from "./words";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "./numbers.css";

const NUMBERS = "/numbers";
const MAILBOXES = "/mailboxes";
const SOCIAL = "/social";

/** Which of the three books a route is listed in: a mailbox and a Page are no numbers, and are never listed with them. */
type Book = "numbers" | "mailboxes" | "social";
const bookOf = (channel: string): Book => (channel === "email" ? "mailboxes" : ON_A_PAGE.has(channel) ? "social" : "numbers");
const HOMES: Record<Book, string> = { numbers: NUMBERS, mailboxes: MAILBOXES, social: SOCIAL };
const TITLES: Record<Book, string> = { numbers: "Numbers", mailboxes: "Mailboxes", social: "Messenger & Instagram" };

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

/** `mail` is the Mailboxes page and `book="social"` the Messenger & Instagram page: what agents answer at that is no number, never listed with numbers. */
export function NumbersPage({ mail = false, book: asBook }: { mail?: boolean; book?: Book }): ReactNode {
  const book: Book = asBook ?? (mail ? "mailboxes" : "numbers");
  const social = book === "social";
  const HOME = HOMES[book];
  // A phone opens on the list, a tap away from each one; a desk opens the first beside it.
  const phone = usePhone();
  const navigate = useNavigate();
  const { number: asked, channel: on = mail ? "email" : social ? "messenger" : "phone" } = useParams();
  const { agents } = useOrg();
  const slugs = useMemo(() => agents.map((one) => one.slug), [agents]);
  const { rows: every, carriers, catalog, refused, reread } = useNumbers();
  const rows = useMemo(() => (every === null ? null : every.filter((one) => bookOf(one.route.channel) === book)), [every, book]);
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("");
  const stopAdding = useCallback(() => setAdding(false), []);

  // A number answers once a channel: the address names both, and the phone's is the number alone.
  const open = rows?.find((one) => one.route.number === asked && one.route.channel === on) ?? rows?.find((one) => one.route.number === asked);
  const wanted = filter.trim().toLowerCase();
  const shownRows = (rows ?? []).filter((one) => wanted === "" || `${one.route.number ?? ""} ${addressSaid(one, carriers)} ${one.route.agent}`.toLowerCase().includes(wanted));

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  if (!phone && rows !== null && asked === undefined && rows[0]?.route.number != null) return <Navigate to={`${HOME}/${encodeURIComponent(rows[0].route.number)}${social ? `/${rows[0].route.channel}` : ""}`} replace />;
  // An address of another book (a mailbox, a Page, written under Numbers before each had a page of its own) opens in its own.
  const elsewhere = open === undefined && asked !== undefined ? every?.find((one) => one.route.number === asked && bookOf(one.route.channel) !== book) : undefined;
  if (elsewhere !== undefined) return <Navigate to={`${HOMES[bookOf(elsewhere.route.channel)]}/${encodeURIComponent(asked ?? "")}${elsewhere.route.channel === "email" ? "" : `/${elsewhere.route.channel}`}`} replace />;
  if (rows !== null && asked !== undefined && open === undefined) return <Navigate to={HOME} replace />;

  const add = (
    <button type="button" className="app-button num-add" onClick={() => setAdding(true)}>
      <Icon name="plus" size={12} />
      Add
    </button>
  );

  return (
    <>
      <PageHead open={open === undefined ? undefined : addressSaid(open, carriers)} />
      <div className="app-layout">
        <aside className="app-list" aria-label={TITLES[book]}>
          <div className="app-list-head">
            <span className="app-list-title">{TITLES[book]}</span>
            <span className="dash-quiet">{rows === null ? "" : rows.length}</span>
            <span className="num-list-add">{add}</span>
          </div>
          <input className="app-input app-search" aria-label={mail ? "Search mailboxes" : social ? "Search Pages" : "Search numbers"} placeholder={mail ? "Search mailboxes" : social ? "Search Pages" : "Search numbers"} value={filter} onChange={(event) => setFilter(event.target.value)} />
          <div className="app-rows">
            {shownRows.map((one) => (
              <NavLink key={`${one.route.number}:${one.route.channel}`} end to={`${HOME}/${encodeURIComponent(one.route.number ?? "")}${mail || one.route.channel === "phone" ? "" : `/${one.route.channel}`}`} className={({ isActive }) => (isActive ? "app-row app-row-on" : "app-row")}>
                <span className="app-row-top">
                  <span className="dash-clip">{addressSaid(one, carriers)}</span>
                  <span className={`app-dot app-dot-${RINGS[one.rings].mood}`} title={ringsSaid(one.rings, one.route.channel)} aria-hidden="true" />
                </span>
                <span className="app-row-under dash-clip">
                  {one.route.agent}
                  {mail || social || one.route.channel === "phone" ? "" : ` · ${CHANNEL_NAMES[one.route.channel]}`}
                </span>
              </NavLink>
            ))}
            {rows !== null && rows.length > 0 && shownRows.length === 0 && <p className="dash-quiet app-none">{mail ? "Nothing by that address." : social ? "No Page by that name." : "Nothing by that number."}</p>}
          </div>
        </aside>
        <div className="app-open">
          <div className="app-main">
            {refused !== null && <p className="app-refused">{refused}</p>}
            {rows === null && <p className="dash-quiet">Reading…</p>}
            {rows !== null && rows.length === 0 && (
              <div className="app-empty">
                <h2 className="app-name">{mail ? `No mailbox in ${WORLD} yet` : social ? `No Facebook Page in ${WORLD} yet` : `No number in ${WORLD} yet`}</h2>
                <p className="dash-quiet">
                  {social ? "A Facebook Page is how a contact reaches an agent on Messenger, and on the Instagram account linked to it. Connect one of yours: the agent answers what is written to either, from them." : mail ? "A mailbox is how a contact reaches an agent by email. Connect one of yours: the agent reads what is written to it and answers from it, in your template." : "A number is how a caller reaches an agent by phone or WhatsApp. Buy one here, bring one from Twilio or your own carrier, or connect WhatsApp."}
                </p>
                <div>
                  <button type="button" className="cfg-save" onClick={() => setAdding(true)}>
                    {mail ? "Connect a mailbox" : social ? "Connect a Page" : "Add a number"}
                  </button>
                </div>
              </div>
            )}
            {open !== undefined && <NumberView key={`${open.route.number}:${open.route.channel}`} row={open} carriers={carriers} catalog={catalog} agents={slugs} onChanged={reread} onGone={() => (reread(), void navigate(HOME, { replace: true }))} />}
            {/* The test line is a phone number to call: it has no place under a mailbox or a number that is written to. */}
            {book === "numbers" && WORLD === "sandbox" && (open === undefined || open.route.channel === "phone") && <TestLine agents={slugs} />}
            {book === "numbers" && rows !== null && rows.length > 0 && <OutboundCard />}
          </div>
        </div>
      </div>
      {adding && <AddNumberPanel agents={slugs} channel={mail ? "email" : social ? "messenger" : null} onAdded={reread} onClose={stopAdding} />}
    </>
  );
}
