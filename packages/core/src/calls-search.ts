/** Call search: server-side via the sessions endpoint when supported, else client-side over loaded rows. */

import { type SessionLine, SessionLineSchema } from "./wire/rest.js";
import { useEffect, useState } from "react";

import { read } from "./api";
import { isLive } from "./calls";
import { useCredentials } from "./credentials";

/** List filters; an empty string means no filter. */
export interface Filter {
  query: string;
  agent: string;
  channel: string;
}

/** Search results: rows, total matches and the next-page cursor. */
export interface Searched {
  rows: SessionLine[];
  total: number;
  next: string | null;
}

// Lenient: a newer gateway may add fields, and rejecting a row would empty the list.
const LooseLine = SessionLineSchema.loose();

const A_PAGE = 50;
const SETTLE_MS = 250;

/** Server results, or null to filter loaded rows client-side. */
export interface ServerSearch {
  found: Searched | null;
  /** False once the gateway returned a plain list (no search support). */
  searches: boolean;
}

/**
 * Server-side search over the sessions endpoint. A response without `total` means an older gateway:
 * `searches` becomes false and the caller filters locally. Fetches `pages` pages of 50, re-runs
 * when `refresh` changes, and does nothing when `wanted` is false.
 */
export function useServerSearch(scope: string, filter: Filter, pages: number, refresh: string, wanted = true): ServerSearch {
  const credentials = useCredentials();
  const [searched, setSearched] = useState<Searched | null>(null);
  const [unsupported, setUnsupported] = useState(false);

  useEffect(() => {
    if (unsupported || !wanted) return;
    let gone = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        const path = scope === "" ? "/v1/sessions" : `/v1/agents/${encodeURIComponent(scope)}/sessions`;
        const params: Record<string, string | number> = { limit: A_PAGE };
        if (filter.query.trim() !== "") params["q"] = filter.query.trim();
        if (filter.agent !== "") params["agent"] = filter.agent;
        if (filter.channel !== "") params["channel"] = filter.channel;
        try {
          // Page with `before`: the endpoint caps `limit` at 200.
          const rows: SessionLine[] = [];
          let total = 0;
          let next: string | null = null;
          for (let page = 0; page < pages; page += 1) {
            if (page > 0 && next === null) break;
            const answer = (await read(credentials, path, next === null ? params : { ...params, before: next })) as Record<string, unknown>;
            if (gone) return;
            if (typeof answer["total"] !== "number") {
              setUnsupported(true);
              return;
            }
            const listed = Array.isArray(answer["calls"]) ? answer["calls"] : [];
            rows.push(...listed.map((row) => LooseLine.parse(row) as SessionLine));
            total = answer["total"];
            next = typeof answer["next"] === "string" ? answer["next"] : null;
          }
          setSearched({ rows, total, next });
        } catch {
          if (!gone) setUnsupported(true);
        }
      })();
    }, SETTLE_MS);
    return () => {
      gone = true;
      window.clearTimeout(timer);
    };
  }, [credentials, scope, filter.query, filter.agent, filter.channel, pages, unsupported, refresh, wanted]);

  return { found: unsupported || !wanted ? null : searched, searches: !unsupported };
}

/** A key that changes when a call starts or ends, to trigger a new search. */
export function floorMoved(lines: readonly SessionLine[]): string {
  return `${lines.length}:${lines[0]?.call ?? ""}:${lines.filter(isLive).length}`;
}

/** Match a query against id, numbers, caller, outcome, agent and channel. */
export function matches(line: SessionLine, query: string): boolean {
  const words = query.trim().toLowerCase();
  if (words === "") return true;
  const digits = words.replace(/[^\d]/g, "");
  const said = [line.call, line.agent, line.from, line.to, line.caller?.name, line.outcome, line.channel].filter(Boolean).join(" ").toLowerCase();
  if (said.includes(words)) return true;
  if (digits.length >= 3) {
    const numbers = `${line.from ?? ""} ${line.to ?? ""} ${line.call}`.replace(/[^\d ]/g, "");
    return numbers.replace(/ /g, "").includes(digits) || numbers.includes(digits);
  }
  return false;
}
