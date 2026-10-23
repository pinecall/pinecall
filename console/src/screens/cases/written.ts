/** A case a person writes in the console: the form's words made the golden the gateway keeps, or why they cannot be. */

import type { Expect, Golden } from "@pinecall/core/wire/rest-goldens";

/** What the New case form holds, as typed. */
export interface Written {
  name: string;
  /** The caller's lines, one a line, in order. */
  lines: string;
  /** The state the call opens in, as JSON; empty opens in the class's own. */
  state: string;
  /** Phrases, comma-separated. */
  says: string;
  not: string;
  /** Tool names, comma-separated. */
  tools: string;
  notTools: string;
  grounded: boolean;
  register: "" | "tu" | "usted";
  heldOut: boolean;
}

export const BLANK: Written = { name: "", lines: "", state: "", says: "", not: "", tools: "", notTools: "", grounded: false, register: "", heldOut: false };

const listed = (typed: string): string[] =>
  typed
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");

/** The golden the form says, or the first reason it says none. */
export function goldenOf(form: Written): { golden: Golden } | { refused: string } {
  const name = form.name.trim();
  if (name === "") return { refused: "Name the case." };
  const said = form.lines
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  if (said.length === 0) return { refused: "Write at least one line the caller says." };
  const state = stateOf(form.state);
  if (typeof state === "string") return { refused: state };
  const says = listed(form.says);
  const not = listed(form.not);
  const tools = listed(form.tools);
  const notTools = listed(form.notTools);
  const expect: Expect = {
    ...(says.length > 0 ? { says } : {}),
    ...(not.length > 0 ? { not } : {}),
    ...(tools.length > 0 ? { tools } : {}),
    ...(notTools.length > 0 ? { not_tools: notTools } : {}),
    ...(form.grounded ? { grounded: true } : {}),
    ...(form.register !== "" ? { register: form.register } : {}),
  };
  return { golden: { name, ...(state === null ? {} : { state }), turns: said.map((say) => ({ say })), ...(Object.keys(expect).length > 0 ? { expect } : {}) } };
}

// The state typed, as the golden carries it: nothing when left empty, else a JSON object, or why not.
function stateOf(typed: string): Record<string, unknown> | null | string {
  if (typed.trim() === "") return null;
  let read: unknown;
  try {
    read = JSON.parse(typed);
  } catch {
    return "The state is not JSON.";
  }
  return isObject(read) ? read : 'The state is a JSON object: {"stage": "book"}.';
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
