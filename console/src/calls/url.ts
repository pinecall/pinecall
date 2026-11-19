/** What the address says about this page: the status, the view, the search and the filters, so a link pasted shows the same list. */

import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router";

import { statusOf, type Status } from "./status";
import { isWritten } from "./threads";

/** Where each of the three pages lives: spoken calls and web chats, the threads a contact writes on a number, the emails. */
export const CALLS = "/calls";
export const MESSAGES = "/messages";
export const EMAILS = "/emails";
export type CallsBase = typeof CALLS | typeof MESSAGES | typeof EMAILS;
export { isWritten };

/** The page a conversation is read on: an email on Emails, a WhatsApp or SMS thread on Messages, anything else on Calls. */
export function baseOf(line: { channel: string | null }): CallsBase {
  if (line.channel === "email") return EMAILS;
  return isWritten(line) ? MESSAGES : CALLS;
}

/** The page this address is on: Emails under /emails, Messages under /messages, Calls anywhere else. */
export function useCallsBase(): CallsBase {
  const path = useLocation().pathname;
  if (path.startsWith(EMAILS)) return EMAILS;
  return path.startsWith(MESSAGES) ? MESSAGES : CALLS;
}

export interface CallsUrl {
  /** `/calls`, `/messages` or `/emails`: where this page's links go. */
  base: CallsBase;
  /** Whether the page lists written conversations: Messages or Emails, nothing spoken. */
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
    written: base !== CALLS,
    table: params.get("view") === "table",
    status: statusOf(params.get("status")),
    query: params.get("q") ?? "",
    agent: params.get("agent") ?? "",
    channel: params.get("channel") ?? "",
    search: written === "" ? "" : `?${written}`,
    ask,
  };
}
