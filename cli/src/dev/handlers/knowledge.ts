/** The console's Docs and Memory screens: this directory's documents pushed and scored, its memory goldens run. */

import { existsSync } from "node:fs";

import { DevRefused } from "@pinecall/agents/client";
import { z } from "zod";

import * as knowledge from "../../knowledge/service/index.js";
import { isDirectory } from "../../project/layout.js";
import { mine, type Here, type Screen } from "./screen.js";

const Push = z.object({ agent: z.string().min(1), base: z.string().min(1).optional() });
const Score = z.object({ agent: z.string().min(1), base: z.string().min(1).optional(), k: z.number().int().min(1).max(100).optional() });
const Recall = z.object({ agent: z.string().min(1), k: z.number().int().min(1).max(100).optional() });
const Extract = z.object({ agent: z.string().min(1) });

/** Docs: the local folder and golden listed, pushed as a base, scored; listing and dropping bases is the gateway's. */
export function knowledgeHandlers(here: Here): Screen {
  const { home, ctx } = here;
  return {
    verbs: {
      "knowledge.roster": async () => {
        const files = isDirectory(home.docs) ? knowledge.markdownUnder(home.docs) : [];
        const golden = existsSync(home.docsGolden) ? home.docsGolden : null;
        return { agent: home.name, base: home.name, directory: home.docs, files: files.length, golden, questions: golden === null ? 0 : countQuestions(golden) };
      },
      "knowledge.push": async (asked) => {
        const wanted = Push.parse(asked);
        mine(here, wanted.agent, "push the knowledge of");
        if (!isDirectory(home.docs)) throw new DevRefused(404, knowledge.NO_DIRECTORY(home.docs));
        const [pushed] = await knowledge.pushDocs(ctx, { dir: home.docs, base: wanted.base ?? home.name });
        return pushed;
      },
      "knowledge.eval": async (asked) => {
        const wanted = Score.parse(asked);
        mine(here, wanted.agent, "score the knowledge of");
        if (!existsSync(home.docsGolden)) throw new DevRefused(404, `no golden at ${home.docsGolden}: a JSON list of {asks, expects}`);
        const [scored] = await knowledge.evalDocs(ctx, { golden: home.docsGolden, base: wanted.base ?? home.name, k: wanted.k, agent: home.name });
        return scored;
      },
    },
  };
}

/** Memory: the recall golden and the extraction cases listed, each run on the gateway, no key leaving this process. */
export function memoryHandlers(here: Here): Screen {
  const { home, ctx } = here;
  const cases = (): string[] => (existsSync(home.memoryCases) ? knowledge.casesIn<{ name?: string }>([home.memoryCases]).map((one) => one.name ?? "") : []);
  return {
    verbs: {
      "memory.roster": async () => {
        const golden = existsSync(home.memoryGolden) ? home.memoryGolden : null;
        return { agent: home.name, golden, questions: golden === null ? 0 : countQuestions(golden), cases: cases() };
      },
      "memory.eval": async (asked) => {
        const wanted = Recall.parse(asked);
        mine(here, wanted.agent, "run the memory goldens of");
        if (!existsSync(home.memoryGolden)) throw new DevRefused(404, `no golden at ${home.memoryGolden}: a JSON list of {holds, asks, expects}`);
        return await knowledge.evalMemory(ctx, { golden: home.memoryGolden, k: wanted.k });
      },
      "memory.extraction": async (asked) => {
        mine(here, Extract.parse(asked).agent, "run the memory goldens of");
        if (cases().length === 0) throw new DevRefused(404, knowledge.NO_CASES);
        return await knowledge.remember(ctx, knowledge.RememberInput.parse({ paths: [home.memoryCases], agent: home.name }));
      },
    },
  };
}

// A golden that holds no list counts none; the verb that runs it says why.
function countQuestions(golden: string): number {
  try {
    return knowledge.questionsOf(golden, "questions").length;
  } catch {
    return 0;
  }
}
