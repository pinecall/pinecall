/** Card and its parts: head, rows, foot, side-pane sections. */

import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router";

export function Card({ children, pad = false, style }: { children: ReactNode; pad?: boolean | undefined; style?: CSSProperties }): ReactNode {
  return (
    <div className={pad ? "ui-card ui-card-pad" : "ui-card"} style={style}>
      {children}
    </div>
  );
}

/** Card head: title, meta and one trailing action. */
export function CardHead({
  title,
  meta,
  action,
  children,
}: {
  title: ReactNode;
  meta?: ReactNode | undefined;
  action?: ReactNode | undefined;
  /** Extra content after the meta. */
  children?: ReactNode | undefined;
}): ReactNode {
  return (
    <div className="ui-card-head">
      {typeof title === "string" ? <span className="ui-card-title">{title}</span> : title}
      {meta !== undefined && <span className="ui-card-meta">{meta}</span>}
      {children}
      {action !== undefined && <span className="ui-card-end">{action}</span>}
    </div>
  );
}

/** Link at the end of a card's head or foot. */
export function CardAction({ to, onClick, children }: { to?: string | undefined; onClick?: () => void; children: ReactNode }): ReactNode {
  if (to !== undefined) {
    return (
      <Link to={to} className="ui-card-action">
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className="ui-card-action" onClick={onClick}>
      {children}
    </button>
  );
}

export function CardFoot({ children }: { children: ReactNode }): ReactNode {
  return <div className="ui-card-foot">{children}</div>;
}

/** Empty-state message. */
export function Empty({ children }: { children: ReactNode }): ReactNode {
  return <div className="ui-empty">{children}</div>;
}

/** An API error message, shown verbatim. */
export function Refused({ children }: { children: ReactNode }): ReactNode {
  return children === null || children === undefined || children === "" ? null : <div className="ui-refused">{children}</div>;
}

/** List row: leading mark, name, subline and trailing content. */
export function Row({
  lead,
  name,
  tag,
  sub,
  end,
  to,
  onClick,
}: {
  lead?: ReactNode | undefined;
  name: ReactNode;
  tag?: ReactNode | undefined;
  sub?: ReactNode | undefined;
  end?: ReactNode | undefined;
  to?: string | undefined;
  onClick?: (() => void) | undefined;
}): ReactNode {
  const body = (
    <>
      {lead}
      <div className="ui-row-main">
        <div className="ui-row-line">
          <span className="ui-row-name">{name}</span>
          {tag}
        </div>
        {sub !== undefined && <div className="ui-row-sub">{sub}</div>}
      </div>
      {end !== undefined && <div className="ui-row-end">{end}</div>}
    </>
  );
  if (to !== undefined) {
    return (
      <Link to={to} className="ui-row ui-row-link">
        {body}
      </Link>
    );
  }
  return (
    <div className={onClick === undefined ? "ui-row" : "ui-row ui-row-link"} onClick={onClick}>
      {body}
    </div>
  );
}

/** Compact side-card row: name, subline, trailing pill. */
export function Item({ name, sub, end, to }: { name: ReactNode; sub?: ReactNode | undefined; end?: ReactNode; to?: string | undefined }): ReactNode {
  const body = (
    <>
      <div className="ui-row-main">
        <div className="ui-item-name">{name}</div>
        {sub !== undefined && <div className="ui-item-sub">{sub}</div>}
      </div>
      {end}
    </>
  );
  return to === undefined ? (
    <div className="ui-item">{body}</div>
  ) : (
    <Link to={to} className="ui-item">
      {body}
    </Link>
  );
}

/** Labelled side-pane section (STATE, ROOM, PROMPT). */
export function SectionLabel({ children, ruled = false }: { children: ReactNode; ruled?: boolean | undefined }): ReactNode {
  return <div className={ruled ? "ui-section-label ui-section-label-ruled" : "ui-section-label"}>{children}</div>;
}

/** Key/value pair. */
export function KV({ label, children, keyWidth }: { label: ReactNode; children: ReactNode; keyWidth?: number | undefined }): ReactNode {
  return (
    <div className="ui-kv">
      <span className="ui-kv-key" style={keyWidth === undefined ? undefined : { width: keyWidth }}>
        {label}
      </span>
      <span className="ui-kv-value">{children}</span>
    </div>
  );
}
