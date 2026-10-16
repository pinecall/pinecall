/** Viewing: the sidebar's picker of whose calls are on screen — every agent of the org, or one — and, in the sandbox, whose copy of it. */

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

import { meIn, somebodyElses } from "../lib/corners";
import { AGENT_SCREENS, screenAt } from "../lib/mode";
import { useOrg } from "../lib/org";
import { orgOf, useWhoami } from "../lib/whoami";
import { useWorld } from "../lib/world";
import { Avatar, Icon } from "../ui";

// What is looked at, the harness and Knowledge are the same rows whoever is in view, so changing
// who keeps them: Calls stays Calls, Simulations stays Simulations, Docs stays Docs. Anything else is one table's alone — an
// agent's Test, the org's Agents — and lands on Overview, the one screen both have at the top.
const LOOKED_AT = new Set(["calls", "quality", "simulations", "personas", "cases", "judges", "monitors", "knowledge", "docs", "memory", "org-docs", "org-memory"]);

/**
 * Where an org-wide path goes when the org's one agent is put in view: the same screen of the
 * agent's, its sub-path and query kept (a call open stays open); undefined for a screen only the
 * org has (its settings, its people), which stays where it is.
 */
function itsOneAgents(pathname: string, search: string, agent: string): string | undefined {
  const screen = screenAt(pathname);
  if (screen === undefined) return undefined;
  if (screen.path === "") return keptFor(pathname, agent);
  if (!LOOKED_AT.has(screen.key)) return undefined;
  return `/a/${encodeURIComponent(agent)}${pathname}${search}`;
}

/** The path the same screen has with `agent` in view, or every agent when it is "". */
function keptFor(pathname: string, agent: string): string {
  const screen = screenAt(pathname);
  const kept = screen !== undefined && LOOKED_AT.has(screen.key) ? screen.path : null;
  if (agent === "") return kept === null ? "/" : `/${kept}`;
  return `/a/${encodeURIComponent(agent)}/${kept ?? (AGENT_SCREENS[0]?.path ?? "overview")}`;
}

/**
 * The trigger says who is in view; the list under it offers every agent of the org and "All
 * agents". Production's agents are the ones deployed; the sandbox lists each copy by whose it is,
 * and a teammate's opens only on a `team` key — the gateway would refuse anyone else.
 */
export function Viewing({ agent }: { agent: string }): ReactNode {
  const whose = useWhoami();
  const me = meIn(whose);
  const { world, corner, lookInto } = useWorld();
  const { held, live, agentsLoaded } = useOrg();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { pathname, search } = useLocation();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent): void => {
      if (box.current !== null && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const production = world === "production";
  const seesTheTeam = !production && whose?.scopes.includes("team") === true;
  const holderOf = (one: HeldAgent): string | null => one.holder?.holder ?? null;
  const openable = (one: HeldAgent): boolean => (production ? holderOf(one) === null : holderOf(one) !== null && (holderOf(one) === me || seesTheTeam));
  const inView = (one: HeldAgent): boolean => one.slug === agent && (production ? holderOf(one) === null : holderOf(one) === (corner ?? me));
  const whoseLine = (one: HeldAgent): string => {
    const holder = holderOf(one);
    if (holder === null) return production ? "deployed" : "shared";
    if (holder === me) return "your copy";
    return `${one.holder?.name ?? holder}'s copy`;
  };
  const words = query.trim().toLowerCase();
  const copies = [...held]
    .filter((one) => words === "" || one.slug.toLowerCase().includes(words))
    .sort((a, b) => a.slug.localeCompare(b.slug) || Number(somebodyElses(a, me)) - Number(somebodyElses(b, me)));
  const lookingAt = corner === null ? undefined : held.find((one) => holderOf(one) === corner);
  const liveOf = (slug: string): number => live.filter((line) => line.agent === slug).length;

  // An org of one agent the person may open has nothing for "All agents" to add: that agent is
  // the view, and an org-wide screen of the ones an agent has opens as its.
  const openableNow = held.filter(openable);
  const onlyOne = new Set(openableNow.map((one) => one.slug)).size === 1;
  const theOne = onlyOne ? (openableNow.find((one) => holderOf(one) === (production ? null : me)) ?? openableNow[0]) : undefined;
  useEffect(() => {
    if (!agentsLoaded || theOne === undefined || agent !== "") return;
    const there = itsOneAgents(pathname, search, theOne.slug);
    if (there === undefined) return;
    const holder = holderOf(theOne);
    if (!production && holder !== me) lookInto(holder);
    void navigate(there, { replace: true });
  }, [agentsLoaded, theOne, agent, pathname, search, production, me, lookInto, navigate]);

  const pick = (one: HeldAgent | null): void => {
    setOpen(false);
    if (one === null) {
      if (corner !== null) lookInto(null);
      void navigate(keptFor(pathname, ""));
      return;
    }
    const holder = holderOf(one);
    if (!production) lookInto(holder === me ? null : holder);
    void navigate(keptFor(pathname, one.slug));
  };

  return (
    <div ref={box} className="view">
      <button
        type="button"
        className={open ? "view-trigger view-trigger-open" : "view-trigger"}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Viewing ${agent === "" ? "all agents" : agent}`}
        title="Whose calls are on screen: every agent, or one"
      >
        {agent === "" ? (
          <span className="view-all" aria-hidden>
            <Icon name="bot" size={13} />
          </span>
        ) : (
          <Avatar size={20} name={agent} letters={agent.slice(0, 1).toUpperCase()} />
        )}
        <span className="view-words">
          <span className="view-name">{agent === "" ? "All agents" : agent}</span>
        </span>
        <span className="view-caret">
          <Icon name="chevrons" size={14} />
        </span>
      </button>

      {open && (
        <div className="view-menu" role="listbox" aria-label="whose calls are on screen">
          {held.length > 6 && <input className="view-find" autoFocus placeholder="Find an agent" value={query} onChange={(event) => setQuery(event.target.value)} />}
          {!onlyOne && (
            <button type="button" role="option" aria-selected={agent === ""} className={agent === "" ? "view-row view-row-on" : "view-row"} onClick={() => pick(null)}>
              <span className="view-all" aria-hidden>
                <Icon name="bot" size={15} />
              </span>
              <span className="view-words">
                <span className="view-row-name">All agents</span>
                <span className="view-row-sub">
                  {whose === null ? "the org" : orgOf(whose)} · {world}
                </span>
              </span>
            </button>
          )}
          {copies.length > 0 && !onlyOne && <div className="view-rule" />}
          {copies.map((one) => {
            const can = openable(one);
            const onAir = liveOf(one.slug);
            return (
              <button
                key={`${one.slug}:${holderOf(one) ?? "org"}`}
                type="button"
                role="option"
                aria-selected={inView(one)}
                className={inView(one) ? "view-row view-row-on" : "view-row"}
                disabled={!can}
                title={can ? undefined : "their copy: it answers them, and they open it from their own console"}
                onClick={() => pick(one)}
              >
                <Avatar size={26} name={one.slug} letters={one.slug.slice(0, 1).toUpperCase()} />
                <span className="view-words">
                  <span className="view-row-name">{one.slug}</span>
                  <span className="view-row-sub">
                    {whoseLine(one)} · {one.channels.join(" · ") || "no doors"}
                  </span>
                </span>
                {onAir > 0 && <span className="view-live">{onAir} live</span>}
              </button>
            );
          })}
          {copies.length === 0 && words === "" && (
            <div className="view-none">
              {production ? "Nothing is deployed in production yet: pinecall start --prod on your server holds it." : "Nothing is running here: pinecall start in a project puts its agents on this list."}
            </div>
          )}
          {corner !== null && (
            <div className="view-corner">
              <span>
                Looking at <b>{lookingAt?.holder?.name ?? corner}</b>'s copy
              </span>
              <button type="button" className="ui-text-action" onClick={() => lookInto(null)}>
                Back to yours
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
