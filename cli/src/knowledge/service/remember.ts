/** `remember`: memory's extraction cases run through the gateway, one model call each, judged by code. */

import { existsSync } from "node:fs";

import { z } from "zod";

import * as api from "../../api/knowledge.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { agentFilesOf, type AgentHome } from "../../project/layout.js";
import { CASES, casesIn, matching, NO_CASES } from "./cases.js";

/** What `remember` takes: the files or folders of cases (the agent's `agents/<name>/test/memory/` when none), the agent, a filter. */
export const RememberInput = z.object({
  paths: z.array(z.string().min(1)).default([]),
  agent: z.string().min(1).optional(),
  file: z.string().min(1).optional(),
  grep: z.string().min(1).optional(),
});
export type RememberInput = z.infer<typeof RememberInput>;

/**
 * Run extraction on the gateway with the org's model and keys, against the memory categories the
 * agent's holder declared: nothing is started here.
 */
export async function remember(ctx: Context, input: RememberInput): Promise<api.ExtractionRun> {
  const choice = { file: input.file, agent: input.agent };
  // Outside an agent folder, fall back to the default path so the error says where cases belong;
  // a project of several agents is told to name one, not where cases belong.
  let home: AgentHome | undefined;
  try {
    home = ctx.agent("remember", choice);
  } catch (refused) {
    if (agentFilesOf(ctx.cwd).length > 1) throw refused;
  }
  const folder = home?.memoryCases ?? CASES;
  const paths = input.paths.length > 0 ? input.paths : [folder];
  if (input.paths.length === 0 && !existsSync(folder)) throw new UsageError(home === undefined ? NO_CASES : NO_CASES.replace(CASES, folder));
  const cases = matching(casesIn<api.ExtractionGolden>(paths), input.grep);
  if (cases.length === 0) throw new UsageError(`no case matched${input.grep === undefined ? "" : ` --grep ${input.grep}`}`);
  // Asked again outside an agent folder, so the refusal names where an agent belongs.
  const agent = home ?? ctx.agent("remember", choice);
  return api.runExtraction(ctx.gateway(), agent.name, cases);
}
