/** Studio as a terminal reads it: the agents, one made, a file pulled or pushed, a tool tried, a deploy, the code written. */

import { bytes, count, yesNo } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { Code, Pulled, Pushed, StudioAgent, TryResult } from "./service.js";

export const NO_AGENTS = "no Studio agent in this org here yet: `pinecall studio new <name>` makes one";

export function agents(found: StudioAgent[]): string[] {
  if (found.length === 0) return [NO_AGENTS];
  return table(
    ["name", "release", "saved by", "stopped"],
    found.map((one) => [one.name, one.release, one.author, yesNo(one.stopped)]),
  );
}

export function made(one: StudioAgent): string {
  return `${one.name}: made in the ${one.env} as release ${one.release} — \`pinecall studio pull ${one.name}\` writes it to a file`;
}

export function pulled(one: Pulled): string {
  return `${one.name}: release ${one.release} written to ${one.file}`;
}

export function pushed({ agent, basedOn, file }: Pushed): string {
  if (agent.release === basedOn) return `${agent.name}: nothing in ${file} changed — still release ${agent.release}`;
  return `${agent.name}: ${file} saved as release ${agent.release} in the ${agent.env}`;
}

/** The status and the time, what went wrong when something did, then the body as the model would read it. */
export function tried(one: TryResult): string[] {
  const lines = [`${one.status ?? "no answer"} · ${one.duration_ms} ms`];
  if (one.error !== null) lines.push(one.error);
  if (one.body !== null && one.body !== undefined) lines.push(...(typeof one.body === "string" ? one.body : JSON.stringify(one.body, null, 2)).replace(/\n$/, "").split("\n"));
  return lines;
}

export function deployed(one: StudioAgent): string {
  return `${one.name}: in production as release ${one.release}, answering from its next call`;
}

export function code(one: Code): string {
  if (one.folder !== null) return `${one.name}: the TypeScript project written to ${one.folder} · ${count(one.files, "file")}`;
  return `${one.name}: the TypeScript project saved as ${one.file ?? `${one.name}.zip`} · ${bytes(one.bytes)}`;
}
