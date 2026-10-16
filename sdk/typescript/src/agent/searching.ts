/** Detect whether a class's source uses `this.knowledge`, with oxc's parser. */

import { parseSync } from "oxc-parser";

// An AST walk, not a regex, so `this.knowledge` in strings or comments does not count. Any
// method in the file counts, not only tools.
const THE_WORD = "knowledge";

/** A loosely typed AST node. */
interface Node {
  type?: string;
  [key: string]: unknown;
}

/**
 * Whether the source reads `this.knowledge`. Sent at registration as `uses_knowledge`, so the
 * gateway can refuse a world with no knowledge base attached at boot instead of mid-call.
 */

export function searchesKnowledge(source: string, file = "agent.tsx"): boolean {
  const parsed = parseSync(file, source, { sourceType: "module" });
  return reaches(parsed.program as unknown as Node);
}

function reaches(node: Node): boolean {
  if (node.type === "MemberExpression") {
    const object = node["object"] as Node;
    const property = node["property"] as Node;
    if (object.type === "ThisExpression" && property.type === "Identifier" && property["name"] === THE_WORD) return true;
  }
  for (const child of Object.values(node)) {
    if (Array.isArray(child)) {
      if (child.some((one) => isNode(one) && reaches(one))) return true;
    } else if (isNode(child) && reaches(child)) {
      return true;
    }
  }
  return false;
}

function isNode(value: unknown): value is Node {
  return typeof value === "object" && value !== null && typeof (value as Node).type === "string";
}
