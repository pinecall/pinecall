/** What each tool did over a window (GET /v1/insights/tools): how often it ran, how often it worked, how long it took, and the last time it failed. */

import { z } from "zod";

import { type Asked } from "./insights";
import { useInsightDoor } from "./insight-door";

// runtime calls/schemas.py: ToolsReport. Loose so a new field does not fail the parse.
const ErrorSchema = z.object({ call: z.string(), at: z.number(), text: z.string() });
const ToolSchema = z.object({ name: z.string(), ran: z.number(), failed: z.number(), median_s: z.number().nullable(), last_error: ErrorSchema.nullable() });
const ToolsSchema = z.looseObject({ day: z.string(), days: z.number(), agent: z.string().nullable(), tools: z.array(ToolSchema) });

export type Tools = z.infer<typeof ToolsSchema>;
export type ToolStat = Tools["tools"][number];

export function useTools(asked: Asked): Tools | null | undefined {
  return useInsightDoor("/v1/insights/tools", (answered) => ToolsSchema.parse(answered), asked);
}
