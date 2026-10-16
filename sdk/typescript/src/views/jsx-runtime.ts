/** The JSX runtime: elements form a tree that renders to text, not DOM. */

/** Anything a component may return; arrays nest and falsy values render nothing. */
export type Child = Element | string | number | boolean | null | undefined | Child[];

export type Props = Record<string, unknown>;

/** A function component from props to renderable children. */
export interface Component {
  (props: Props): Child;
  /** Rendered on one line inside its parent instead of as its own paragraph. */
  inline?: boolean;
}

/** A JSX element: a tag and its props (including `children`). */
export interface Element {
  readonly kind: "element";
  readonly type: string | Component | typeof Fragment;
  readonly props: Props;
}

/** `<>…</>`: groups siblings without adding text. */
export const Fragment = Symbol.for("pinecall.views.fragment");

/** Element factory for the automatic JSX runtime; also exported as `jsxs` and `jsxDEV`. */
export function jsx(type: Element["type"], props: Props): Element {
  return { kind: "element", type, props: props ?? {} };
}

export { jsx as jsxs, jsx as jsxDEV };

function childrenOf(props: Props): Child {
  return (props["children"] ?? null) as Child;
}

// Collapse JSX source newlines and indentation into single spaces.
function paragraph(text: string): string {
  return text.replace(/\s*\n\s*/g, " ").replace(/[ \t]{2,}/g, " ").trim();
}

/** Render a child inline. Strings keep their spacing, so `{name} tiene cita` stays intact. */
export function renderInline(child: Child): string {
  if (child === null || child === undefined || typeof child === "boolean") return "";
  if (typeof child === "string") return child;
  if (typeof child === "number") return String(child);
  if (Array.isArray(child)) return child.map(renderInline).join("");
  const { type, props } = child;
  if (typeof type === "function") return renderInline(type(props));
  return renderInline(childrenOf(props));
}

/**
 * Render a child as text: siblings become paragraphs separated by a blank line, falsy values
 * render nothing, and strings are trimmed.
 */
export function renderToText(child: Child): string {
  return blocks(child).join("\n\n");
}

/** Render each child as a separate block, dropping empty ones. */
export function blocks(child: Child): string[] {
  if (child === null || child === undefined || typeof child === "boolean") return [];
  if (typeof child === "string") return child.trim() ? [child.trim()] : [];
  if (typeof child === "number") return [String(child)];
  if (Array.isArray(child)) return child.flatMap(blocks);
  const { type, props } = child;
  if (typeof type === "function") {
    if (type.inline) {
      const line = paragraph(renderInline(child));
      return line ? [line] : [];
    }
    return blocks(type(props));
  }
  // `<p>` is the only intrinsic tag; other lowercase tags render just their children.
  if (type === "p") {
    const line = paragraph(renderInline(childrenOf(props)));
    return line ? [line] : [];
  }
  return blocks(childrenOf(props));
}

/** JSX types TypeScript resolves through `jsxImportSource`. */
type TextElement = Element;

export declare namespace JSX {
  type Element = TextElement;
  /** An intrinsic tag or a function component; class components are not supported. */

  type ElementType = string | ((props: never) => Child) | Component;
  interface ElementChildrenAttribute {
    children: object;
  }
  interface IntrinsicElements {
    p: { children?: Child };
  }
}
