/** What a served process prints: the wire entry line by line for the CLI, or a few lines for a person. */

import type { Entry } from "../wire/envelope.js";

/** One `--events` line: the entry as the gateway wrote it, without the log's bookkeeping. */
export function eventLine(entry: Entry): string {
  return JSON.stringify({ type: entry.type, agent: entry.agent, call: entry.call, data: entry.data });
}

/** A line for a person reading the process, or null for an entry worth no line. */
export function personLine(entry: Entry): string | null {
  const data = entry.data as Record<string, unknown>;
  const said = (mark: string, text: unknown): string => `${entry.agent}  ${mark} ${String(text)}`;
  switch (entry.type) {
    case "agent.registered":
      return said("·", `answering as ${String(data["app"])}`);
    case "turn.user":
      return said("‹", data["text"]);
    case "turn.agent":
      return said("›", data["text"]);
    case "tool.call":
      return said("→", data["name"]);
    case "error":
      return said("✗", data["message"]);
    default:
      return null;
  }
}
