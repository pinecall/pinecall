/** The MCP's tool pages under docs/mcp/: each tool's sentence, its manual, its parameters read off its own schema, and a real call. */

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { z } from "zod";

import type { Tool } from "../src/mcp/tool.js";
import { STAGES, type Stage } from "../src/mcp/tools/index.js";

export const PAGES = fileURLToPath(new URL("../docs/mcp/", import.meta.url));

/** One real call of a tool, as Pinecall Cloud answered it: recorded, anonymized, trimmed. */
export interface Example {
  args: Record<string, unknown>;
  answer: unknown;
}

export type Examples = Record<string, Example[]>;

/** The examples kept beside the pages. */
export function examples(): Examples {
  return JSON.parse(readFileSync(`${PAGES}examples.json`, "utf8")) as Examples;
}

/** One stage's page, as it is committed under docs/mcp/<page>.md. */
export function pageOf(stage: Stage, kept: Examples): string {
  const lines = [
    `# ${stage.stage}`,
    "",
    `Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the`,
    "tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.",
    "",
  ];
  for (const tool of stage.tools) lines.push(...toolOf(tool, kept[tool.name] ?? []));
  return `${lines.join("\n").trimEnd()}\n`;
}

/** What a JSON Schema property takes, in a person's words. */
interface Property {
  type?: string | string[];
  enum?: unknown[];
  const?: unknown;
  items?: Property;
  anyOf?: Property[];
  description?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  properties?: Record<string, Property>;
}

function toolOf(tool: Tool, calls: Example[]): string[] {
  const schema = z.toJSONSchema(z.object(tool.schema)) as { properties?: Record<string, Property>; required?: string[] };
  const properties = Object.entries(schema.properties ?? {});
  const lines = [`## \`${tool.name}\``, "", tool.description, "", tool.manual, ""];
  if (properties.length === 0) lines.push("It takes nothing.", "");
  else {
    lines.push("| parameter | takes | | what it is |", "|---|---|---|---|");
    for (const [name, property] of properties) {
      const needed = (schema.required ?? []).includes(name) ? "required" : "";
      lines.push(`| \`${name}\` | ${takes(property)} | ${needed} | ${(property.description ?? "").replaceAll("|", "\\|")} |`);
    }
    lines.push("");
  }
  for (const call of calls) lines.push(...callOf(call));
  return lines;
}

function takes(property: Property): string {
  if (property.enum !== undefined) return property.enum.map((one) => `\`${String(one)}\``).join(" · ");
  if (property.const !== undefined) return `\`${String(property.const)}\``;
  if (property.anyOf !== undefined) return property.anyOf.map(takes).join(" or ");
  const range = rangeOf(property);
  if (property.type === "array") return `a list of ${property.items === undefined ? "values" : plural(takes(property.items))}`;
  if (property.type === "integer") return `a whole number${range}`;
  if (property.type === "number") return `a number${range}`;
  if (property.type === "boolean") return "true or false";
  if (property.type === "object") return property.properties === undefined ? "an object" : `an object of ${Object.keys(property.properties).map((key) => `\`${key}\``).join(" · ")}`;
  return "text";
}

// zod's .int() bounds a number by the safe integers: a bound no person types is no bound.
function rangeOf(property: Property): string {
  const most = property.maximum !== undefined && property.maximum < Number.MAX_SAFE_INTEGER ? property.maximum : undefined;
  const least = property.minimum !== undefined && property.minimum > Number.MIN_SAFE_INTEGER ? property.minimum : undefined;
  if (least !== undefined && most !== undefined) return ` ${least}–${most}`;
  if (least !== undefined) return ` ${least} or more`;
  return most === undefined ? "" : ` up to ${most}`;
}

function plural(said: string): string {
  return said.startsWith("`") ? said : said.replace(/^an? /, "").replace(/^text$/, "texts").replace(/^whole number/, "whole numbers");
}

// A long text field of the answer (a prompt, a page) reads as text under the JSON, not as one escaped line.
function callOf(call: Example): string[] {
  const answer = call.answer as Record<string, unknown>;
  const long = Object.entries(answer ?? {}).filter(([, value]) => typeof value === "string" && value.includes("\n") && value.length > 200);
  const shown = long.length === 0 ? answer : Object.fromEntries(Object.entries(answer).map(([key, value]) => [key, long.some(([one]) => one === key) ? "(below)" : value]));
  const lines = ["```json title=\"called with\"", JSON.stringify(call.args, null, 2), "```", "", "```json title=\"answered\"", JSON.stringify(shown, null, 2), "```", ""];
  for (const [key, value] of long) lines.push(`\`\`\`text title="${key}"`, String(value).trimEnd(), "```", "");
  return lines;
}

// `scripts/mcp-pages` writes them; test/mcp/pages.test.ts fails a page that is not what this writes.
if (process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1]) {
  const kept = examples();
  for (const stage of STAGES) writeFileSync(`${PAGES}${stage.page}.md`, pageOf(stage, kept));
  process.stdout.write(`wrote ${STAGES.map((stage) => `docs/mcp/${stage.page}.md`).join(" ")}\n`);
}
