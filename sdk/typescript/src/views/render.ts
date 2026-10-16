/** Render the prompt as blocks for the runtime, or as a readable page. */

import { type PromptRegion } from "../wire/defs.js";

import type { Agent } from "../agent/agent.js";
import { layout, type Blocks } from "./layout.js";

/** The agent's current prompt, block by block in send order. */
export function promptOf(agent: Agent): Blocks {
  return layout(agent);
}

/** Section header for the printed prompt: the block name, with its region when given. */
export function headerFor(name: string, region?: PromptRegion): string {
  return region === undefined ? `── ${name} ──` : `── ${name} (${region}) ──`;
}

/** The prompt as one readable page (static blocks, history, dynamic), as `--show-prompt` prints it. */

export function showPrompt(agent: Agent): string {
  const { blocks, history } = promptOf(agent);
  const section = (name: string, text: string, region?: PromptRegion): string =>
    `${headerFor(name, region)}\n${text}`.trimEnd();
  const of = (region: PromptRegion): string[] =>
    blocks.filter((block) => block.region === region).map((block) => section(block.name, block.text, region));
  return [...of("static"), section("history", history), ...of("dynamic")].join("\n\n");
}
