/** What the address says about this page: the status, the view, the search and the filters, so a link pasted shows the same list. */

import { useCallback } from "react";
import { useSearchParams } from "react-router";

import { statusOf, type Status } from "./status";

export interface CallsUrl {
  table: boolean;
  status: Status;
  query: string;
  agent: string;
  channel: string;
  /** The address's search, with its `?` when there is one. */
  search: string;
  /** Write one value into the address; an empty one takes it out. */
  ask: (name: string, value: string) => void;
}

export function useCallsUrl(): CallsUrl {
  const [params, setParams] = useSearchParams();
  const ask = useCallback(
    (name: string, value: string): void => {
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          if (value === "") next.delete(name);
          else next.set(name, value);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const written = params.toString();
  return {
    table: params.get("view") === "table",
    status: statusOf(params.get("status")),
    query: params.get("q") ?? "",
    agent: params.get("agent") ?? "",
    channel: params.get("channel") ?? "",
    search: written === "" ? "" : `?${written}`,
    ask,
  };
}
