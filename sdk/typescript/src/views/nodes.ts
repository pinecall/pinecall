/** Render view JSX to a node tree the console draws (not DOM). */

import { Fragment, type Child, type Component, type Element, type Props } from "./jsx-runtime.js";

/** Badge tone; the console maps it to colours. */
export type Tone = "neutral" | "good" | "warn" | "bad";

/**
 * One node of a view. The set is closed and drawn by the console's own components, so tenant
 * panels cannot inject styles or scripts.
 */
export type ViewNode =
  | { tag: "panel"; title: string | null; children: ViewNode[] }
  | { tag: "rows"; children: ViewNode[] }
  | { tag: "row"; label: string; value: string }
  | { tag: "stat"; label: string; value: string }
  | { tag: "table"; columns: string[]; rows: string[][] }
  | { tag: "badge"; tone: Tone; text: string }
  | { tag: "text"; text: string };

/** A panel component, with a builder for its node. */
export interface Panels extends Component {
  /** Set on built-in panel tags; other functions are called as ordinary components. */
  node?: (props: Props, children: ViewNode[]) => ViewNode | null;
}

/** Format a value for display; null, undefined and booleans become "". */
export function said(value: unknown): string {
  if (value === null || value === undefined || typeof value === "boolean") return "";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  return String(value);
}

/**
 * Render a child to view nodes. Panel tags become nodes, other components are called, strings and
 * numbers become text. Components inside the tree must be synchronous; only the view itself may be async.
 */
export function renderToNodes(child: Child): ViewNode[] {
  if (child === null || child === undefined || typeof child === "boolean") return [];
  if (typeof child === "string") return child.trim() === "" ? [] : [{ tag: "text", text: child.trim() }];
  if (typeof child === "number") return [{ tag: "text", text: String(child) }];
  if (Array.isArray(child)) return child.flatMap(renderToNodes);
  return nodesOfElement(child);
}

function nodesOfElement(element: Element): ViewNode[] {
  const { type, props } = element;
  if (type === Fragment) return renderToNodes(childrenOf(props));
  if (typeof type === "function") {
    const tag = type as Panels;
    if (tag.node === undefined) return renderToNodes(tag(props));
    const node = tag.node(props, renderToNodes(childrenOf(props)));
    return node === null ? [] : [node];
  }
  // Views have no intrinsic tags: a lowercase tag renders only its children.

  return renderToNodes(childrenOf(props));
}

function childrenOf(props: Props): Child {
  return (props["children"] ?? null) as Child;
}
