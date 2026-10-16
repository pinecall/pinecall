/** Prompt layout: named blocks in send order, static, then history, then dynamic. */

import { type PromptBlockSpec } from "../wire/defs.js";

import { changes, internalsOf, type Agent } from "../agent/agent.js";
import { docOf, toolsOf } from "../agent/tools.js";
import { tagged } from "./components.js";
import { channelRulesFor, PROTOCOLS, RULES } from "./built-in-rules.js";
import { renderToText } from "./jsx-runtime.js";

/** A rendered prompt block: name, region and text. */
export interface Block extends PromptBlockSpec {
  text: string;
}

/** The rendered prompt. Only `dynamic` blocks may differ between turns, to keep the cache prefix. */
export interface Blocks {
  /** Blocks in send order; the history goes between the static and dynamic ones. */
  blocks: Block[];
  /** `collapse()` summaries, for the printed page; the runtime owns the actual history. */
  history: string;
}

// Static blocks are cached; the view is the only dynamic block and comes last, after the history,
// so per-turn guidance is what the model reads last.
const BLOCKS = [
  { name: "identity", region: "static", text: identityBlock },
  // Filled by the gateway from the agent's settings (`pinecall agent knowledge`); the app sends "".
  { name: "knowledge", region: "static", text: () => "" },
  { name: "tools", region: "static", text: toolsBlock },
  { name: "view", region: "dynamic", text: viewBlock },
] as const satisfies readonly (PromptBlockSpec & { text: (agent: Agent) => string })[];

/** Prompt block names and regions, in send order. */
export const PROMPT_BLOCKS: readonly PromptBlockSpec[] = BLOCKS.map(({ name, region }) => ({ name, region }));

/** Render every prompt block in send order. */
export function layout(agent: Agent): Blocks {
  const blocks = BLOCKS.map(({ name, region, text }) => ({ name, region, text: text(agent) }));
  return { blocks, history: collapsedHistory(agent) };
}

/** Class docstring, built-in rules and protocols, and the channel's. Reads no state. */
function identityBlock(agent: Agent): string {
  return paragraphs([docOf(agent) ?? "", tagged("rules", RULES), tagged("protocols", PROTOCOLS), channelBlock(agent)]);
}

// Static because a call never changes its channel or medium. With no call (an offline prompt), a
// phone call's.
function channelBlock(agent: Agent): string {
  if (agent.channelRules === false) return "";
  const call = internalsOf(agent).call;
  return tagged("channel", channelRulesFor(call?.channel, call?.medium ?? "voice"));
}

// Lists every declared tool, visible or not, so this block stays static. Schemas go on the wire.
function toolsBlock(agent: Agent): string {
  const docs = toolsOf(agent)
    .map((declared) => `- ${declared.name}: ${declared.spec.description}`)
    .join("\n");
  return tagged("tools", docs);
}

// Only the tenant's `render()` output. Recalled facts and retrieved chunks reach the model as tool
// results, never here (runtime docs/security/prompt-injection.md).
function viewBlock(agent: Agent): string {
  return renderToText(agent.render());
}

/** Summaries left by `collapse()`; the runtime owns the actual turns. */

function collapsedHistory(agent: Agent): string {
  return changes(agent)
    .filter((change) => change.field === "@summary")
    .map((change) => String(change.next))
    .join("\n\n");
}

function paragraphs(parts: string[]): string {
  return parts.filter((part) => part.trim()).join("\n\n");
}
