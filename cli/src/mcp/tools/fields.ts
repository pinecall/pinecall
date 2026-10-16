/** The fields many tools take, declared once so every schema says them in the same words. */

import { z } from "zod";

import { ToolRefused } from "../tool.js";

/** Which agent of the project, when it has several. */
export const AGENT = z.string().optional().describe("the agent's name; the project's only agent when left out");

/** How long a tool that runs long waits before answering what it has. */
export const WAIT_S = 25;

/** A host that waits longer than this for one tool call gives up on it. */
export const LONGEST_WAIT_S = 50;

export const WAIT = z.number().int().min(0).max(LONGEST_WAIT_S).optional().describe(`how long to wait before answering what is known so far, in seconds; ${WAIT_S} when left out`);

/** A value a tool must have for an action; refused by name when it is missing. */
export function needed(value: string | undefined, name: string): string {
  if (value === undefined || value === "") throw new ToolRefused(`${name} is needed for this action`);
  return value;
}
