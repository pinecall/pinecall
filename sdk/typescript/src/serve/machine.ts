/** Developer view of an agent's tools: current stage, and which tools are visible and why. */

import { stageOf, stagesOf } from "../agent/stages.js";
import { toolsOf, visibleToolsOf, type ErasedToolOptions } from "../agent/tools.js";
import { headerFor } from "../views/render.js";

/** List every declared tool, marking the visible ones and what gates each. For developers only. */
export function showMachine(agent: object): string {
  const visible = new Set(visibleToolsOf(agent).map((declared) => declared.name));
  const declarations = toolsOf(agent);
  if (declarations.length === 0) return `${header(agent)}\n\n  this agent declares no tools`;
  const width = Math.max(...declarations.map((declared) => declared.name.length));
  const lines = declarations.map((declared) => {
    const shown = visible.has(declared.name);
    const mark = shown ? "●" : "○";
    return `  ${mark} ${declared.name.padEnd(width)}  ${gatedBy(agent, declared.options, shown)}`;
  });
  return [header(agent), "", ...lines].join("\n");
}

function header(agent: object): string {
  const stage = stageOf(agent);
  return stage === undefined ? headerFor("tools") : `${headerFor("tools")} stage: ${stage}`;
}

// Flags a tool hidden in its own stage, since that is always the `when` predicate's doing.
function gatedBy(agent: object, options: ErasedToolOptions, shown: boolean): string {
  const stages = stagesOf(options);
  if (stages === undefined) return options.when === undefined ? "always" : "when(state)";
  const here = stageOf(agent);
  const named = stages.join(" · ");
  const hiddenInItsOwnStage = !shown && here !== undefined && stages.includes(here);
  return hiddenInItsOwnStage ? `${named} · when(state) says no` : named;
}
