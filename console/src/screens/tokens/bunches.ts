/** The token list sorted into what a person looks for: servers, their own keys by device, and the revoked. */

import type { Listed } from "./door";

/** Keys sharing one label and owner — a console login made on each visit is one bunch, not sixty rows. */
export interface Bunch {
  label: string;
  rows: Listed[];
  /** The most recent use among them, as a time, or null when none was ever used. */
  lastUsed: number | null;
}

const usedAt = (row: Listed): number | null => (row.last_used_at === null ? null : Date.parse(row.last_used_at));

/** Most recently used first; never used last. */
const recent = (one: number | null, other: number | null): number => (other ?? -1) - (one ?? -1);

export function bunches(rows: Listed[]): Bunch[] {
  const by = new Map<string, Listed[]>();
  for (const row of rows) {
    const key = `${row.label ?? row.fingerprint}\u0000${row.name ?? ""}`;
    by.set(key, [...(by.get(key) ?? []), row]);
  }
  return [...by.values()]
    .map((group) => {
      const sorted = [...group].sort((one, other) => recent(usedAt(one), usedAt(other)));
      const lastUsed = sorted.map(usedAt).find((at) => at !== null) ?? null;
      return { label: sorted[0]?.label ?? sorted[0]?.fingerprint.slice(0, 12) ?? "", rows: sorted, lastUsed };
    })
    .sort((one, other) => recent(one.lastUsed, other.lastUsed));
}

export interface Sorted {
  servers: Listed[];
  mine: Bunch[];
  revoked: Listed[];
}

export function sorted(rows: Listed[]): Sorted {
  const live = rows.filter((row) => row.revoked_at === null);
  return {
    servers: [...live.filter((row) => row.kind === "server")].sort((one, other) => recent(usedAt(one), usedAt(other))),
    mine: bunches(live.filter((row) => row.kind === "person")),
    revoked: rows.filter((row) => row.revoked_at !== null),
  };
}
