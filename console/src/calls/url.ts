/** What the address says about this page: the status, the view, the search and the filters, so a link pasted shows the same list. */

import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router";

import { statusOf, type Status } from "./status";
import { isWritten } from "./threads";

/** Where each of the two pages lives: spoken calls and web chats, and the threads a contact writes on. */
export const CALLS = "/calls";
export const MESSAGES = "/messages";
export { isWritten };

/** The page this address is on: Messages under /messages, Calls anywhere else. */
export function useCallsBase(): typeof CALLS | typeof MESSAGES {
  return useLocation().pathname.startsWith(MESSAGES) ? MESSAGES : CALLS;
}

export interface CallsUrl {
  /** `/calls` or `/messages`: where this page's links go. */
  base: typeof CALLS | typeof MESSAGES;
  /** Whether this is Messages: the WhatsApp and SMS threads, and nothing spoken. */
  written: boolean;
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
  const base = useCallsBase();
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
    base,
    written: base === MESSAGES,
    table: params.get("view") === "table",
    status: statusOf(params.get("status")),
    query: params.get("q") ?? "",
    agent: params.get("agent") ?? "",
    channel: params.get("channel") ?? "",
    search: written === "" ? "" : `?${written}`,
    ask,
  };
}
