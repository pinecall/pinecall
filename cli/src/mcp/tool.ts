/** A tool of the MCP server: what a model reads about it, what it takes, and the service it calls. */

import { z } from "zod";

import type { Context } from "../context.js";
import { PinecallError } from "../errors.js";
import type { Session } from "./session.js";

/** The field every tool takes: production when true, the sandbox otherwise; the server sets `ctx.env` from it. */
export const PROD = z.boolean().optional().describe("true acts in production; left out or false, in the sandbox");

/** What a tool runs with: a verb's Context (its env set from `prod`) and the server's session. */
export interface ToolContext extends Context {
  readonly session: Session;
}

/** A tool as declared, typed by its own schema. `manual` is the paragraph the server's instructions carry about it. */
interface Declared<Shape extends z.ZodRawShape> {
  name: string;
  /** One sentence: what the tool does, for the host's tool list. */
  description: string;
  schema: Shape;
  /** When to use it and what it answers, read by the model once, in the server's instructions. */
  manual: string;
  handler: (args: z.infer<z.ZodObject<Shape>>, ctx: ToolContext) => Promise<unknown>;
  /** The values of its answer no scrubbing may hide: a console link's one-use code, and nothing else. */
  reveals?: (result: unknown) => string[];
}

/** A tool as the server lists it: its schema checks what a host sends before the handler sees it. */
export interface Tool {
  name: string;
  description: string;
  manual: string;
  schema: z.ZodRawShape;
  call(args: unknown, ctx: ToolContext): Promise<unknown>;
  reveals?: ((result: unknown) => string[]) | undefined;
}

/** Declare a tool; its handler receives arguments already checked against its schema, `prod` taken out. */
export function tool<Shape extends z.ZodRawShape>(declared: Declared<Shape>): Tool {
  const schema = { ...declared.schema, prod: PROD };
  const checked = z.object(schema);
  return {
    name: declared.name,
    description: declared.description,
    manual: declared.manual,
    schema,
    call: (args, ctx) => {
      const { prod: _prod, ...rest } = checked.parse(args ?? {}) as Record<string, unknown>;
      return declared.handler(rest as z.infer<z.ZodObject<Shape>>, ctx);
    },
    reveals: declared.reveals,
  };
}

/** A refusal the model can act on: its words are the whole answer, with no stack. */
export class ToolRefused extends PinecallError {
  override readonly name = "ToolRefused";
}
