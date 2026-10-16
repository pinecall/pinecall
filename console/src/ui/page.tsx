/** Screen page layout: scrolling column, title, lede and actions. */

import type { ReactNode } from "react";

export type PageWidth = 1180 | 1060 | 900 | 760;

export function Page({
  width = 1180,
  tight = false,
  children,
}: {
  width?: PageWidth | undefined;
  /** 16px between blocks instead of 18: the list screens. */
  tight?: boolean | undefined;
  children: ReactNode;
}): ReactNode {
  const classes = ["ui-page"];
  if (tight) classes.push("ui-page-tight");
  if (width !== 1180) classes.push(`ui-page-${width}`);
  return (
    <div className={classes.join(" ")} data-page>
      {children}
    </div>
  );
}

/** Page head: title, lede and actions. */
export function PageHead({
  title,
  lede,
  ledeWidth,
  back,
  actions,
}: {
  title: ReactNode;
  lede?: ReactNode | undefined;
  /** Caps a two-line lede at the design's 620–660px. */
  ledeWidth?: number | undefined;
  back?: ReactNode | undefined;
  actions?: ReactNode | undefined;
}): ReactNode {
  return (
    <div className="ui-head">
      <div className="ui-head-words" style={ledeWidth === undefined ? undefined : { maxWidth: ledeWidth }}>
        {back}
        <h1 className="ui-title">{title}</h1>
        {lede !== undefined && <p className={ledeWidth === undefined ? "ui-lede" : "ui-lede ui-lede-long"}>{lede}</p>}
      </div>
      {actions !== undefined && <div className="ui-head-actions">{actions}</div>}
    </div>
  );
}
