/** `serve prompt`: the prompt a state produces, and the stage and tools it shows, offline. */

import { parseArgs } from "node:util";

import { ChannelSchema, MediumSchema } from "../wire/defs.js";

import { showPrompt } from "../views/render.js";
import type { Io } from "./io.js";
import { CannotServe, instanceFor, loadServed } from "./load.js";
import { showMachine } from "./machine.js";

/** Load the class, open it in the state the pairs name, and print its prompt. No gateway, no key. */
export async function prompt(argv: string[], io: Io): Promise<number> {
  const { values } = parseArgs({
    args: argv,
    options: {
      file: { type: "string" },
      slug: { type: "string" },
      state: { type: "string", multiple: true },
      channel: { type: "string", default: "phone" },
      medium: { type: "string" },
      "show-machine": { type: "boolean", default: false },
    },
  });
  if (values.file === undefined || values.slug === undefined) {
    throw new CannotServe("serve prompt takes the agent's --file and the --slug it is served as");
  }
  const channel = ChannelSchema.safeParse(values.channel);
  const medium = MediumSchema.optional().safeParse(values.medium);
  if (!channel.success || !medium.success) {
    throw new CannotServe("--channel is phone, web or whatsapp, and --medium is voice or text");
  }
  const agent = instanceFor(await loadServed(values.file, values.slug), channel.data, medium.data);
  agent.startIn(stateOf(values.state ?? []));
  const machine = values["show-machine"] === true ? `\n\n${showMachine(agent)}` : "";
  io.out.write(`${showPrompt(agent)}${machine}\n`);
  return 0;
}

/** `field=json` pairs as the state they name; a value that is not JSON is refused by its field. */
export function stateOf(pairs: string[]): Record<string, unknown> {
  const state: Record<string, unknown> = {};
  for (const pair of pairs) {
    const at = pair.indexOf("=");
    if (at <= 0) throw new CannotServe(`--state ${pair}: a field, =, and its value as JSON`);
    const field = pair.slice(0, at);
    try {
      state[field] = JSON.parse(pair.slice(at + 1));
    } catch {
      throw new CannotServe(`--state ${field}: its value is not JSON`);
    }
  }
  return state;
}
