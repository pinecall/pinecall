/** What a class may do once its agent is registered, before its first call: publish for the pages that show it. */

import type { Camel } from "../wire/codec.js";
import type { RecordedLine } from "../wire/rest-lines.js";

/** Handed to `static onServe`: the agent's slug, and what it may publish for pages. */
export interface Serve {
  /** The slug the agent is served as. */
  slug: string;
  /** Record each text once in the agent's voice, in order: an MP3's URL, its length, when each word is said. */
  record(texts: string[]): Promise<Camel<RecordedLine>[]>;
  /** Publish a JSON object under a name, for any page to read with no key. */
  publish(name: string, document: Record<string, unknown>): Promise<void>;
  /** One line for the person who started the agent, in their terminal. */
  say(line: string): void;
}
