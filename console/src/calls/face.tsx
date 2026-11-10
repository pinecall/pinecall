/** A person's letters in a round, tinted by their name so the same person looks the same, with a dot when they are on a call. */

import type { CSSProperties, ReactNode } from "react";

import { initialsOf } from "@pinecall/core/initials";

const TONES = ["--accent", "--blue", "--pink", "--good", "--warn"] as const;

function toneOf(name: string): string {
  let sum = 0;
  for (const letter of name) sum += letter.charCodeAt(0);
  return `var(${TONES[sum % TONES.length] ?? "--accent"})`;
}

export function Face({ name, letters, on = null, big = false }: { name: string; letters?: string | undefined; on?: "asking" | "live" | null; big?: boolean }): ReactNode {
  const classes = ["calls-face", big ? "calls-face-big" : "", on === null ? "" : `calls-face-${on}`].join(" ");
  return (
    <span className={classes} style={{ "--tone": toneOf(name) } as CSSProperties} aria-hidden="true">
      {letters ?? initialsOf(name)}
    </span>
  );
}
