/** Panel components for views (`@pinecall/agents/panels`), drawn by the console. */

import type { Props } from "./jsx-runtime.js";
import { said, type Panels, type Tone, type ViewNode } from "./nodes.js";

// Calling the function body means the tag was used in a prompt; throw instead of leaking panel text.
const NOT_A_PROMPT = (tag: string): string => `<${tag}> belongs to a view, not to a prompt: render() writes text, view() draws a panel`;

function tag(name: string, node: (props: Props, children: ViewNode[]) => ViewNode | null): Panels {
  const component: Panels = () => {
    throw new TypeError(NOT_A_PROMPT(name));
  };
  component.node = node;
  return component;
}

/** A titled section; several stack vertically. */
export const Panel = tag("Panel", (props, children) => ({
  tag: "panel",
  title: props["title"] === undefined ? null : said(props["title"]),
  children,
}));

/** A list of labelled rows. */
export const Rows = tag("Rows", (_props, children) => ({ tag: "rows", children }));

/** A labelled line, e.g. `Alta · 12 Mar 2024`. Value from `value` or the children. */
export const Row = tag("Row", (props, children) => ({
  tag: "row",
  label: said(props["label"]),
  value: props["value"] === undefined ? textOf(children) : said(props["value"]),
}));

/** A prominent labelled number. */
export const Stat = tag("Stat", (props) => ({ tag: "stat", label: said(props["label"]), value: said(props["value"]) }));

/** A table. Each of `rows` is an array in column order, or an object keyed by column name. */
export const Table = tag("Table", (props) => {
  const columns = Array.isArray(props["columns"]) ? props["columns"].map(said) : [];
  const given = Array.isArray(props["rows"]) ? props["rows"] : [];
  return { tag: "table", columns, rows: given.map((row) => cells(row, columns)) };
});

/** A status badge with a `tone`: neutral, good, warn or bad. */
export const Badge = tag("Badge", (props, children) => ({
  tag: "badge",
  tone: toneOf(props["tone"]),
  text: props["text"] === undefined ? textOf(children) : said(props["text"]),
}));

/** A line of text. */
export const Text = tag("Text", (_props, children) => {
  const text = textOf(children);
  return text === "" ? null : { tag: "text", text };
});

const TONES: readonly Tone[] = ["neutral", "good", "warn", "bad"];

function toneOf(given: unknown): Tone {
  return typeof given === "string" && (TONES as readonly string[]).includes(given) ? (given as Tone) : "neutral";
}

function cells(row: unknown, columns: string[]): string[] {
  if (Array.isArray(row)) return row.map(said);
  if (row !== null && typeof row === "object") return columns.map((column) => said((row as Record<string, unknown>)[column]));
  return [said(row)];
}

function textOf(
children: ViewNode[]): string {
  return children
    .map((node) => (node.tag === "text" ? node.text : ""))
    .filter((text) => text !== "")
    .join(" ");
}
