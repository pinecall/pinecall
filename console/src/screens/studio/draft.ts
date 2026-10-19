/** What the editor starts a new part with, how a greeting is chosen, and the words the instructions and headers may name. */

import type { Collect, Definition, Greeting, Header, HttpTool, Param, ParamType } from "./door";

/** The types a parameter or a collected field may be, as the select lists them. */
export const PARAM_TYPES: readonly ParamType[] = ["string", "number", "integer", "boolean"];

/** The methods a tool's request may use. */
export const METHODS: readonly HttpTool["method"][] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

/** What the instructions may name; the call fills each in when it starts. */
export const PLACEHOLDERS: readonly string[] = ["{{call.from}}", "{{call.to}}", "{{call.today}}", "{{call.channel}}", "{{caller.name}}", "{{metadata.KEY}}"];

/** Names the gateway keeps for its own tools: a tool of the agent's may not take one. */
export const RESERVED_TOOLS: readonly string[] = ["collect", "end_call", "current_date", "recall", "search", "say"];

/** A tool's or a field's name: a letter, then letters, digits and underscores. */
export const A_NAME = /^[A-Za-z][A-Za-z0-9_]*$/;

// runtime studio/schemas.py: TOOL_TIMEOUT_S and LONGEST_TOOL_S.
export const TOOL_TIMEOUT_S = 10;
export const LONGEST_TOOL_S = 30;

/** A header's value naming one of the env's secrets. */
export const secretIn = (name: string): string => `{{secrets.${name}}}`;

export const aHeader = (): Header => ({ name: "", value: "" });

export const aParam = (): Param => ({ name: "", type: "string", description: "", required: true });

/** A new tool, numbered so two new ones never share a name. */
export function aTool(taken: readonly HttpTool[]): HttpTool {
  let at = taken.length + 1;
  while (taken.some((tool) => tool.name === `tool_${at}`)) at += 1;
  return { name: `tool_${at}`, description: "", method: "GET", url: "https://", headers: [], params: [], announce: null, timeout_s: TOOL_TIMEOUT_S };
}

/** Data collection as it is first switched on: one field, and the call ended once it is in. */
export function aCollect(): Collect {
  return { fields: [aParam()], end_when_done: true, closing: "Thank the caller, say goodbye, and end the call.", send_to: null, headers: [] };
}

/** How a call opens: nobody speaks first, the agent says fixed words, or the model opens from an instruction. */
export type Opening = "none" | "say" | "reply";

export function openingOf(greeting: Greeting | null | undefined): Opening {
  if (greeting === null || greeting === undefined) return "none";
  return typeof greeting.say === "string" ? "say" : "reply";
}

/** The greeting's words, whichever of the two it is. */
export function greetingText(greeting: Greeting | null | undefined): string {
  return greeting?.say ?? greeting?.reply ?? "";
}

/** The greeting an opening and its words make: exactly one of `say` and `reply`, or none. */
export function greetingOf(opening: Opening, text: string): Greeting | null {
  if (opening === "none") return null;
  return opening === "say" ? { say: text } : { reply: text };
}

/** Whether the editor holds anything the release it read does not. */
export function changed(draft: Definition, saved: Definition): boolean {
  return JSON.stringify(draft) !== JSON.stringify(saved);
}

/** Why a tool's name would be refused, before the gateway is asked; null when it would not be. */
export function toolNameRefused(name: string): string | null {
  if (!A_NAME.test(name)) return "A tool's name starts with a letter, then letters, digits or _.";
  if (RESERVED_TOOLS.includes(name)) return `${name} is the gateway's own tool: pick another name.`;
  return null;
}
