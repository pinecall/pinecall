/** What every console screen's handlers stand on, and how a failure of theirs is told to the console. */

import { DevRefused } from "@pinecall/agents/client";
import type { DevVerb } from "@pinecall/agents/wire";
import { ZodError } from "zod";

import type { Context } from "../../context.js";
import { errorMessage, GatewayError, UsageError } from "../../errors.js";
import type { AgentHome } from "../../project/layout.js";
import type { Served } from "../serving.js";

/** Handlers keyed by wire verb. */
export type Verbs = Partial<Record<DevVerb, (asked: unknown) => Promise<unknown>>>;

/** What every screen's handlers stand on: the context, the agent's home on disk, and the process serving it. */
export interface Here {
  ctx: Context;
  home: AgentHome;
  served: Served;
}

/** A screen's handlers, and what it lets go when the console is closed. */
export interface Screen {
  verbs: Verbs;
  close?: () => Promise<void>;
}

/** A refusal as the console reads it: FastAPI's `{detail}` with its status. */
export function refusalOf(failed: unknown): DevRefused {
  if (failed instanceof DevRefused) return failed;
  if (failed instanceof GatewayError) return new DevRefused(failed.status, failed.detail);
  if (failed instanceof ZodError) return new DevRefused(422, failed.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; "));
  if (failed instanceof UsageError) return new DevRefused(422, failed.message);
  return new DevRefused(500, errorMessage(failed));
}

/** The agent a request names must be the one this directory holds; another is refused with where to run. */
export function mine(here: Here, asked: string, doing: string): void {
  if (asked !== here.home.name) throw new DevRefused(409, `this process runs in ${here.home.name}'s directory: to ${doing} ${asked}, run \`pinecall start\` there`);
}
