/** The hold melody: what a caller hears while a tool runs or the model is slow — the runtime's, none, or a file of the org's — and after how long. */

import { readFileSync, statSync } from "node:fs";
import { basename, resolve } from "node:path";

import { z } from "zod";

import * as api from "../../api/agents.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { agentNamed } from "./settings.js";

export type { HoldMelody } from "../../api/agents.js";

/** The gateway's own ceiling on an upload, said here before the bytes travel. */
const LARGEST_UPLOAD = 20 * 1024 * 1024;
const AN_AFTER = "after takes seconds of quiet, 0 to 30 (0.8, 1.5), or default for the runtime's own";

/** `melody after`: seconds, or `default` for the runtime's wait. */
export const AfterInput = z.union([z.literal("default"), z.coerce.number({ error: AN_AFTER }).min(0, AN_AFTER).max(30, AN_AFTER)], { error: AN_AFTER });
export type AfterInput = z.infer<typeof AfterInput>;

export async function showMelody(ctx: Context, agent: string | undefined): Promise<api.HoldMelody> {
  return api.getMelody(ctx.gateway(), agentNamed(ctx, agent));
}

/** A wav, an mp3, an ogg, a flac or an m4a, up to five minutes, as the agent's melody from the next call. */
export async function uploadMelody(ctx: Context, agent: string | undefined, file: string): Promise<api.HoldMelody> {
  const path = resolve(file);
  let size: number;
  try {
    size = statSync(path).size;
  } catch {
    throw new UsageError(`no file at ${path}`);
  }
  if (size > LARGEST_UPLOAD) throw new UsageError(`${file} is over 20 MB: a melody loops, so a short one does`);
  return api.uploadMelody(ctx.gateway(), agentNamed(ctx, agent), readFileSync(path), basename(path));
}

/** The runtime's melody back, or nothing at all; an uploaded file is forgotten either way, the wait kept. */
export async function chooseMelody(ctx: Context, agent: string | undefined, played: "default" | "off"): Promise<api.HoldMelody> {
  return api.chooseMelody(ctx.gateway(), agentNamed(ctx, agent), played);
}

export async function waitBeforeMelody(ctx: Context, agent: string | undefined, after: AfterInput): Promise<api.HoldMelody> {
  return api.waitBeforeMelody(ctx.gateway(), agentNamed(ctx, agent), after === "default" ? null : after);
}
