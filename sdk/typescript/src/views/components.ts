/** Prompt components: rules, protocols, sections and examples, rendered to text. */

import { blocks, renderInline, renderToText, type Child, type Component, type Props } from "./jsx-runtime.js";

/** A single rule, rendered as a bullet line. */
export const Rule: Component = (props) => `- ${renderInline(children(props)).trim()}`;
Rule.inline = true;

/** A `<rules>` block, one child per line. */
export const Rules: Component = (props) => tagged("rules", lines(props));

/** A `<protocols>` block: behaviour that holds in every state. */
export const Protocols: Component = (props) => tagged("protocols", lines(props));

/** A section with a `## title` heading and its children as paragraphs. */
export const Section: Component = (props) => {
  const body = renderToText(children(props));
  const title = String(props["title"] ?? "").trim();
  if (!title) return body;
  return body ? `## ${title}\n\n${body}` : `## ${title}`;
};

/** An `<example>` block, so the model reads it as an example rather than an instruction. */
export const Example: Component = (props) => tagged("example", renderToText(children(props)));

/** A paragraph; equivalent to the `<p>` tag. */
export const p: Component = (props) => renderInline(children(props));
p.inline = true;

/** Wrap `body` in `<name>` tags, or return "" when it is empty. */

export function tagged(name: string, body: string): string {
  return body ? `<${name}>\n${body}\n</${name}>` : "";
}

function children(props: Props): Child {
  return (props["children"] ?? null) as Child;
}

function lines(props: Props): string {
  return blocks(children(props)).join("\n");
}
