/** Small marks: pill, dot, avatar initials, tag, bar. */

import type { ReactNode } from "react";

import { initialsOf } from "@pinecall/core/initials";

export type Tone = "green" | "amber" | "red" | "indigo" | "violet" | "gray" | "muted";

export function Pill({ tone, small = false, children }: { tone: Tone; small?: boolean | undefined; children: ReactNode }): ReactNode {
  return <span className={`ui-pill ui-pill-${tone}${small ? " ui-pill-small" : ""}`}>{children}</span>;
}

export function Tag({ children }: { children: ReactNode }): ReactNode {
  return <span className="ui-tag">{children}</span>;
}

export function Dot({ tone, small = false }: { tone?: "green" | "amber" | undefined; small?: boolean }): ReactNode {
  const classes = ["ui-dot"];
  if (small) classes.push("ui-dot-small");
  if (tone !== undefined) classes.push(`ui-dot-${tone}`);
  return <span className={classes.join(" ")} aria-hidden />;
}

export type Tint = "violet" | "green" | "pink" | "amber" | "indigo" | "red" | "ink";

// Avatar tints, in design order.
const TINTS: readonly Tint[] = ["violet", "green", "pink", "amber", "indigo"];

/** Tint for the n-th item of a list. */
export function tintAt(index: number): Tint {
  return (["violet", "pink", "green", "amber", "indigo"] as const)[index % 5] ?? "violet";
}

/** Stable tint for a name, from the sum of its char codes. */
export function tintOf(name: string): Tint {
  let sum = 0;
  for (const letter of name) sum = (sum + (letter.codePointAt(0) ?? 0)) % 9973;
  return TINTS[sum % TINTS.length] ?? "violet";
}

export type AvatarSize = 20 | 26 | 28 | 36 | 38;

export function Avatar({
  name,
  letters,
  tint,
  size = 28,
  round = false,
}: {
  name: string;
  /** Replaces the initials, e.g. "W" for a web visitor. */
  letters?: string | undefined;
  tint?: Tint | undefined;
  size?: AvatarSize | undefined;
  round?: boolean | undefined;
}): ReactNode {
  const classes = ["ui-avatar", `ui-tint-${tint ?? tintOf(name)}`];
  if (size === 26) classes.push("ui-avatar-26");
  if (size === 36 || size === 38) classes.push("ui-avatar-36");
  if (round) classes.push("ui-avatar-round");
  if (size === 38) classes.push("ui-avatar-38");
  const style = size === 20 ? { width: 20, height: 20, borderRadius: 6, fontSize: 9.5 } : undefined;
  return (
    <span className={classes.join(" ")} style={style} aria-hidden>
      {letters ?? initialsOf(name)}
    </span>
  );
}

/** Bar filled to a fraction, e.g. a latency against its budget. */
export function Bar({ share, color, height }: { share: number; color?: string | undefined; height?: number }): ReactNode {
  const width = `${Math.max(0, Math.min(1, share)) * 100}%`;
  return (
    <span className="ui-bar" style={height === undefined ? undefined : { height }}>
      <span className="ui-bar-fill" style={{ width, background: color }} />
    </span>
  );
}
