/** The JSON Schema a model answers by, from a zod schema or as given: what a flow's extract step sends. */

import { z } from "zod";

/** The JSON Schema a model answers by: a zod schema's, or the JSON Schema given as it is. */
export function jsonSchemaOf(schema: unknown): Record<string, unknown> {
  return schema instanceof z.ZodType ? (z.toJSONSchema(schema) as Record<string, unknown>) : (schema as Record<string, unknown>);
}
