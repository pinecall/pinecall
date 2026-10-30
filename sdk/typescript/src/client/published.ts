// What an agent publishes for pages and pushes as its base: lines recorded once in its voice, JSON documents any page reads with no key, its documents.

import { type KnowledgeFile } from "../wire/agent-config.js";
import { toCamel, type Camel } from "../wire/codec.js";
import { RecordedLinesSchema, type RecordedLine } from "../wire/rest-lines.js";
import { KnowledgePushedSchema, type KnowledgePushed } from "../wire/rest-retrieval.js";
import { detailOf } from "./answered.js";
import { knowledgeUrl, linesUrl, publishedUrl } from "./endpoints.js";
import { PinecallError } from "./frames.js";
import { signed, type World } from "./signed.js";

/** The gateway and the key a request goes with. */
export interface Door {
  url: string;
  apiKey: string;
  env?: World | undefined;
}

/** Each text as a line in the agent's voice, in order: recorded once, so asking again costs nothing. */
export async function recordLines(door: Door, agent: string, texts: string[]): Promise<Camel<RecordedLine>[]> {
  const answered = await fetch(linesUrl(door.url, agent), {
    method: "POST",
    headers: { ...signed(door.apiKey, door.env), "content-type": "application/json" },
    body: JSON.stringify({ texts }),
  });
  const text = await answered.text();
  if (!answered.ok) throw new PinecallError(`record lines: the gateway answered ${answered.status}: ${detailOf(text)}`);
  return toCamel(RecordedLinesSchema.parse(JSON.parse(text)).lines);
}

/** Write the files into the base by their paths, the base's other files kept: what `pinecall docs push` sends. */
export async function pushKnowledge(door: Door, base: string, files: KnowledgeFile[]): Promise<Camel<KnowledgePushed>> {
  const answered = await fetch(knowledgeUrl(door.url, base), {
    method: "PUT",
    headers: { ...signed(door.apiKey, door.env), "content-type": "application/json" },
    body: JSON.stringify({ files }),
  });
  const text = await answered.text();
  if (!answered.ok) throw new PinecallError(`push ${base}: the gateway answered ${answered.status}: ${detailOf(text)}`);
  return toCamel(KnowledgePushedSchema.parse(JSON.parse(text)));
}

/** Publish a JSON object under a name, over the one before it, for any page to read with no key. */
export async function publish(door: Door, agent: string, name: string, document: Record<string, unknown>): Promise<void> {
  const answered = await fetch(publishedUrl(door.url, agent, name), {
    method: "PUT",
    headers: { ...signed(door.apiKey, door.env), "content-type": "application/json" },
    body: JSON.stringify(document),
  });
  if (!answered.ok) throw new PinecallError(`publish ${name}: the gateway answered ${answered.status}: ${detailOf(await answered.text())}`);
}
