/** Calls: every conversation of the org, or of the agent in view — as threads beside the call open, or as one table — through the status picked. */

import type { ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";

import { useOrg } from "../../lib/org";
import { Segmented } from "../../ui";
import { Inbox } from "../inbox";
import { ConversationList } from "./list";
import { keeps, statusOf, STATUSES } from "./status";
import "./calls.css";

/**
 * The one place calls are read. The URL is the state: `?view=table` is the table, `?status=` the
 * chip picked, `?focus=1` the call alone on the screen, and the call open is the path's
 * (`/calls/:call`). Both views read the same list the sidebar's live count is folded from
 * (`@pinecall/core/use-floor`), so the two never disagree.
 */
export function Calls(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const [search, setSearch] = useSearchParams();
  const { lines, floorError, agents } = useOrg();
  const table = search.get("view") === "table";
  const status = statusOf(search.get("status"));
  const focus = search.get("focus") === "1";
  const mine = agent === "" ? lines : lines.filter((line) => line.agent === agent);
  const kept = mine.filter((line) => keeps(status, line));
  // Calls from agents nobody holds any more stay filterable: their calls happened.
  const slugs = [...new Set([...agents.map((one) => one.slug), ...lines.map((line) => line.agent)])].sort();

  const asked = (name: string, value: string): void => {
    const next = new URLSearchParams(search);
    if (value === "") next.delete(name);
    else next.set(name, value);
    setSearch(next, { replace: true });
  };

  return (
    <div className="calls">
      {!focus && (
        <div className="calls-bar">
          <h1 className="calls-title">Calls</h1>
          <div className="calls-chips" role="group" aria-label="which calls">
            {STATUSES.map((one) => {
              const count = mine.filter((line) => keeps(one.value, line)).length;
              return (
                <button key={one.value} type="button" className={status === one.value ? "calls-chip calls-chip-on" : "calls-chip"} aria-pressed={status === one.value} onClick={() => asked("status", one.value)}>
                  {one.name}
                  <span className={one.value === "asking" && count > 0 ? "calls-chip-count calls-chip-count-asking" : "calls-chip-count"}>{count}</span>
                </button>
              );
            })}
          </div>
          <span className="calls-grow" />
          <Segmented
            options={[
              { value: "threads", label: "Threads" },
              { value: "table", label: "Table" },
            ]}
            value={table ? "table" : "threads"}
            onChange={(chosen) => asked("view", chosen === "table" ? "table" : "")}
          />
        </div>
      )}
      {table ? (
        <div className="calls-table">
          <ConversationList lines={kept} error={floorError} agent={agent} agents={slugs} status={status} />
        </div>
      ) : (
        <Inbox listed={kept} focus={focus} onFocus={() => asked("focus", focus ? "" : "1")} />
      )}
    </div>
  );
}
