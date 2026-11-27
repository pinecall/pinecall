/** What the address says about this page: the kind of conversation, the status, the view, the search and the filters, so a link pasted shows the same list. */

import { useCallback } from "react";
import { useSearchParams } from "react-router";

import { statusOf, type Status } from "./status";
import { isWritten } from "./threads";

/** The one page every conversation is listed on, whatever it came by: a call, a chat, a message, an email. */
export const CALLS = "/calls";
export { isWritten };

/** What the page can be narrowed to, in the order the picker shows them; `""` is every one. `?type=` in the address. */
export const TYPES = [
  { value: "", label: "Everything" },
  { value: "phone", label: "Phone calls" },
  { value: "web-call", label: "Web calls" },
  { value: "web-chat", label: "Web chat" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "sms", label: "SMS" },
  { value: "email", label: "Email" },
  { value: "messenger", label: "Messenger" },
  { value: "instagram", label: "Instagram" },
] as const;

export type CallType = (typeof TYPES)[number]["value"];

/** The kind the address asked for, or every one when it asked for none this page knows. */
export function typeAsked(asked: string | null): CallType {
  return TYPES.find((one) => one.value === asked)?.value ?? "";
}

/** The channel the gateway is asked for when it searches a kind; none for every kind. */
export function channelOf(type: CallType): string {
  return type === "" ? "" : type.startsWith("web") ? "web" : type;
}

// A kind is asked of the gateway, never filtered out of the newest calls the page holds: on 2026-11-19 picking
// "Phone calls" listed nothing in an org with thirteen, because two of its fifty newest conversations were by phone.
/** What the gateway is asked for, for the kind picked and with the tests or without them. */
export function askedOf(url: Pick<CallsUrl, "type" | "tests" | "agent">, query: string): { query: string; agent: string; channel: string; medium?: "voice" | "text"; tests?: boolean } {
  const medium = url.type === "web-call" ? { medium: "voice" as const } : url.type === "web-chat" ? { medium: "text" as const } : {};
  return { query, agent: url.agent, channel: channelOf(url.type), ...medium, ...(url.tests ? {} : { tests: false }) };
}

export interface CallsUrl {
  /** Where this page's links go. */
  base: typeof CALLS;
  table: boolean;
  status: Status;
  /** The kind picked; `""` is every one. */
  type: CallType;
  /** Whether simulations and golden runs are listed with the real conversations. */
  tests: boolean;
  query: string;
  agent: string;
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
    base: CALLS,
    table: params.get("view") === "table",
    status: statusOf(params.get("status")),
    type: typeAsked(params.get("type")),
    tests: params.get("tests") === "1",
    query: params.get("q") ?? "",
    agent: params.get("agent") ?? "",
    search: written === "" ? "" : `?${written}`,
    ask,
  };
}
