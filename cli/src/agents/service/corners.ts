/** The three corners of an agent's settings — yours, the team's, production's — and how a write lands on one. */

import type { TuningAnswer, TuningBody, TuningRow } from "@pinecall/agents/wire";

import * as api from "../../api/agents.js";
import type { GatewayClient } from "../../api/client.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";

export type { TuningAnswer, TuningBody, TuningRow } from "@pinecall/agents/wire";

/** Maps the corner's config to the next one; the whole set travels, so a field left out is erased. */
export type Change = (config: TuningBody) => TuningBody;

/** What a settings write answered, named for a terminal: the corner written and its new version. */
export interface CornerWritten {
  agent: string;
  /** `your corner`, `the team's corner` or `production`. */
  corner: string;
  version: number | null;
  answer: TuningAnswer;
}

/** The three corners as this key sees them: its own, the team's, production's. */
export async function readSettings(ctx: Context, agent: string): Promise<TuningAnswer> {
  return api.getSettings(ctx.gateway(), agent);
}

/** The corner this key reads: its own if it has one, else the team's. */
export function cornerRead<Row>(answer: { yours: Row | null; team: Row | null }): Row | null {
  return answer.yours ?? answer.team;
}

/**
 * Whether this key writes a corner of its own: a person's key in the sandbox. A server's token
 * (`pc_test_` is the sandbox's), and every key in production, writes the org's own. A person whose
 * corner is still empty reads `yours: null` too, which is why the answer alone cannot say.
 */
export function holdsACorner(gw: GatewayClient): boolean {
  return gw.env === "sandbox" && !gw.key.startsWith("pc_test_");
}

/** The row a write lands on: the team's on `--team` or for a key with no corner, else this key's own, null until its first write. */
export function cornerWritten<Row>(answer: { yours: Row | null; team: Row | null }, team: boolean, gw: GatewayClient): Row | null {
  return team || !holdsACorner(gw) ? answer.team : answer.yours;
}

/** The row a write starts from: the team's on `--team`, else what this key reads, so the whole set travels. */
export function rowToStartFrom<Row>(answer: { yours: Row | null; team: Row | null }, team: boolean): Row | null {
  return team ? answer.team : cornerRead(answer);
}

/** The version a write is guarded by: the newest of the corner it lands on, 0 when that corner is empty. */
export function versionGuarded(answer: { yours: { version: number } | null; team: { version: number } | null }, team: boolean, gw: GatewayClient): number {
  return cornerWritten(answer, team, gw)?.version ?? 0;
}

/** Whether two rows set the same: key order is nothing, a field set to the value it holds is the same row. */
export function sameSettings(one: TuningBody, other: TuningBody): boolean {
  const sorted = (body: TuningBody): string =>
    JSON.stringify(body, (_key, value: unknown) => (value !== null && typeof value === "object" && !Array.isArray(value) ? Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b))) : value));
  return sorted(one) === sorted(other);
}

// The corner's own row with what the change moved: a field the change set to something else than
// it reads is the corner's now; one it took out leaves the corner's row; the rest is left as it is.
function movedOnto(own: TuningBody, read: TuningBody, changed: TuningBody): TuningBody {
  const next: Record<string, unknown> = { ...own };
  const fields = new Set([...Object.keys(read), ...Object.keys(changed)]) as Set<keyof TuningBody>;
  for (const field of fields) {
    if (!(field in changed)) delete next[field];
    else if (!sameSettings({ [field]: changed[field] } as TuningBody, { [field]: read[field] } as TuningBody)) next[field] = changed[field];
  }
  return next as TuningBody;
}

/** The name of the corner a write lands on, for output. */
export function cornerName(answer: { world: string }, team: boolean, gw: GatewayClient): string {
  if (answer.world === "production") return "production";
  return team || !holdsACorner(gw) ? "the team's corner" : "your corner";
}

/**
 * Write one change as the next version of a corner. The change is made to what this key reads (the
 * team's on `--team`), and only the fields it moved are written into the corner it lands on: the
 * gateway reads a call's settings field by field from the nearest corner that sets each, so a
 * field copied down from the team's would stop following the team's. The version it is guarded by
 * is the newest of that corner, 0 when it is empty. `before` sees the row read first, for a check
 * that writes nothing.
 */
export async function writeCorner(ctx: Context, agent: string, team: boolean, change: Change, note: string | null, before?: (row: TuningRow | null) => void): Promise<CornerWritten> {
  const gw = ctx.gateway();
  const standing = await api.getSettings(gw, agent);
  const read = rowToStartFrom(standing, team);
  before?.(read);
  const own = cornerWritten(standing, team, gw)?.config ?? {};
  const next = movedOnto(own, read?.config ?? {}, change(read?.config ?? {}));
  // The gateway writes no version for it either; said here, before anything travels.
  if (sameSettings(next, own)) throw new UsageError(`nothing changes in ${cornerName(standing, team, gw)}: it already reads so`);
  const answer = await api.putSettings(gw, agent, { config: next, if_version: versionGuarded(standing, team, gw), note, team });
  // Name the corner the gateway actually wrote, which differs from the flag for a key with no corner.
  return { agent, corner: cornerName(answer, team, gw), version: cornerWritten(answer, team, gw)?.version ?? null, answer };
}
