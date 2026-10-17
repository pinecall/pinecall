/** Every tool the MCP server offers, by the stage a person meets it at. */

import type { Tool } from "../tool.js";
import { link, login, whoami } from "./accounts.js";
import { agent, lexicon, pipeline, voiceSample, voices } from "./agents.js";
import { monitors, telemetry, webhook } from "./alerts.js";
import { call, calls, chat, supervise } from "./calls.js";
import { consoleUrl, prompt, start, status, stop } from "./dev.js";
import { cases, evalTool, personas, runs, simulate, test } from "./evals.js";
import { deploy } from "./hosting.js";
import { judges, judging, usage } from "./judging.js";
import { docs, memory, remember } from "./knowledge.js";
import { providers } from "./providers.js";
import { runtime } from "./runtime.js";
import { project } from "./scaffold.js";
import { docsSearch, getDoc } from "./site.js";
import { callbacks, carriers, line, numbers } from "./telephony.js";

/** One stage of the journey and its tools. */
export interface Stage {
  stage: string;
  /** Its page under docs/mcp/, every tool's parameters and a real answer. */
  page: string;
  tools: readonly Tool[];
}

export const STAGES: readonly Stage[] = [
  { stage: "Getting started", page: "getting-started", tools: [whoami, login, link, project, runtime] },
  { stage: "Holding the agent, and talking to it", page: "holding-and-talking", tools: [start, stop, status, chat, prompt, consoleUrl] },
  { stage: "The agent's settings", page: "settings", tools: [agent, lexicon, voices, voiceSample] },
  { stage: "Calls, and what they run on", page: "calls", tools: [calls, call, pipeline, providers, telemetry, monitors, webhook, usage] },
  { stage: "The phone", page: "phone", tools: [line, numbers, carriers, callbacks] },
  { stage: "Supervising a live call", page: "supervising", tools: [supervise] },
  { stage: "Testing", page: "testing", tools: [test, runs, cases, simulate, personas, judges, judging, evalTool] },
  { stage: "Knowledge and memory", page: "knowledge-and-memory", tools: [docs, memory, remember] },
  { stage: "Going live, and the docs", page: "going-live", tools: [deploy, docsSearch, getDoc] },
];

export const TOOLS: readonly Tool[] = STAGES.flatMap((one) => one.tools);
