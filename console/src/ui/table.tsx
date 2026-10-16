/** Grid table: a label header and rows on the same columns. */

import type { ReactNode } from "react";
import { Link } from "react-router";

/** Header row. A label ending in `>` is right-aligned: `"Today>"`. */
export function TableHead({ columns, labels, padding }: { columns: string; labels: readonly string[]; padding?: string | undefined }): ReactNode {
  return (
    <div className="ui-table-head" style={{ gridTemplateColumns: columns, padding }}>
      {labels.map((label, index) =>
        label.endsWith(">") ? (
          <span key={index} style={{ textAlign: "right" }}>
            {label.slice(0, -1)}
          </span>
        ) : (
          <span key={index}>{label}</span>
        ),
      )}
    </div>
  );
}

/** A row: link, button-like or plain. */
export function TableRow({
  columns,
  to,
  onClick,
  padding,
  children,
}: {
  columns: string;
  to?: string | undefined;
  onClick?: (() => void) | undefined;
  padding?: string | undefined;
  children: ReactNode;
}): ReactNode {
  const style = { gridTemplateColumns: columns, padding };
  if (to !== undefined) {
    return (
      <Link to={to} className="ui-table-row ui-table-row-link" style={style}>
        {children}
      </Link>
    );
  }
  return (
    <div className={onClick === undefined ? "ui-table-row" : "ui-table-row ui-table-row-link"} style={style} onClick={onClick}>
      {children}
    </div>
  );
}
