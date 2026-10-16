/** Agent view door: whether the agent declares a view, and its tree for one conversation. */

import { z } from "zod";

import { GatewayError, read, type Credentials } from "@pinecall/core/api";
import { dev } from "../../lib/dev";

// Mirrors the framework's src/views/nodes.ts; the console may not import the framework
// (test/the-imports.test.ts). Unknown tags are dropped, not refused, so newer apps still render.
export type ViewNode =
  | { tag: "panel"; title: string | null; children: ViewNode[] }
  | { tag: "rows"; children: ViewNode[] }
  | { tag: "row"; label: string; value: string }
  | { tag: "stat"; label: string; value: string }
  | { tag: "table"; columns: string[]; rows: string[][] }
  | { tag: "badge"; tone: "neutral" | "good" | "warn" | "bad"; text: string }
  | { tag: "text"; text: string };

const NodeSchema: z.ZodType<ViewNode> = z.lazy(() =>
  z.union([
    z.object({ tag: z.literal("panel"), title: z.string().nullable(), children: z.array(NodeSchema) }),
    z.object({ tag: z.literal("rows"), children: z.array(NodeSchema) }),
    z.object({ tag: z.literal("row"), label: z.string(), value: z.string() }),
    z.object({ tag: z.literal("stat"), label: z.string(), value: z.string() }),
    z.object({ tag: z.literal("table"), columns: z.array(z.string()), rows: z.array(z.array(z.string())) }),
    z.object({ tag: z.literal("badge"), tone: z.enum(["neutral", "good", "warn", "bad"]), text: z.string() }),
    z.object({ tag: z.literal("text"), text: z.string() }),
  ]),
);

const DrawnSchema = z.looseObject({ name: z.string(), nodes: z.array(NodeSchema) });

/** The panel's title and tree. */
export type Drawn = z.infer<typeof DrawnSchema>;

// Only `view` is read; absent means the agent has no panel (runtime types/agent.py).
const DeclarationSchema = z.looseObject({ view: z.string().nullish() });

/** The agent's declared view name, or null. */
export async function readDeclaredView(credentials: Credentials, agent: string): Promise<string | null> {
  const said = DeclarationSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/config`));
  return said.view ?? null;
}

/** The agent app's view for one conversation, or null when the gateway or app is too old to serve it. */
export async function readView(credentials: Credentials, agent: string, contact: string, call: string): Promise<Drawn | null> {
  try {
    return DrawnSchema.parse(await dev(credentials, agent, "view.render", { contact, call }));
  } catch (refused) {
    if (refused instanceof GatewayError && (refused.status === 404 || refused.status === 405)) return null;
    throw refused;
  }
}
