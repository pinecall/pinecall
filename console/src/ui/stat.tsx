/** Stat cards in a wrapping grid. */

import type { ReactNode } from "react";

export function Stats({ min, children }: { min: number; children: ReactNode }): ReactNode {
  return (
    <div className="ui-stats" style={{ gridTemplateColumns: `repeat(auto-fit,minmax(${min}px,1fr))` }}>
      {children}
    </div>
  );
}

export type StatSize = "big" | "medium" | "small" | "fact";

/**
 * One stat. Sizes: big (home, 25px + delta), medium (overview, 22px + "of N"), small (usage and
 * evals, 21px), fact (session facts, 13.5px, a word).
 */
export function Stat({
  label,
  value,
  of,
  delta,
  tone,
  size = "medium",
  accent = false,
}: {
  label: ReactNode;
  value: ReactNode;
  of?: ReactNode | undefined;
  delta?: ReactNode | undefined;
  tone?: "up" | "down" | "flat" | "green" | "red" | undefined;
  size?: StatSize | undefined;
  accent?: boolean | undefined;
}): ReactNode {
  const classes = ["ui-stat"];
  if (size !== "medium") classes.push(`ui-stat-${size}`);
  if (accent) classes.push("ui-stat-accent");
  const valueStyle = tone === "green" ? { color: "var(--green)" } : tone === "red" ? { color: "var(--red)" } : undefined;
  return (
    <div className={classes.join(" ")}>
      <div className="ui-stat-label">{label}</div>
      {size === "big" ? (
        <div className="ui-stat-line">
          <span className="ui-stat-value">{value}</span>
          {delta !== undefined && (
            <span className={tone === "up" ? "ui-stat-delta ui-stat-delta-up" : tone === "down" ? "ui-stat-delta ui-stat-delta-down" : "ui-stat-delta"}>
              {delta}
            </span>
          )}
        </div>
      ) : (
        <div className="ui-stat-value" style={valueStyle}>
          {value}
          {of !== undefined && <span className="ui-stat-of"> {of}</span>}
        </div>
      )}
    </div>
  );
}
