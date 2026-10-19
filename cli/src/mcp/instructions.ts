/** The server's instructions: the journey from nothing to an agent answering, and the tools by stage. Each tool's manual rides its own description. */

import type { Stage } from "./tools/index.js";

const JOURNEY = `Pinecall runs voice and chat agents written as a class. These tools take a person from an empty
folder to an agent on Pinecall, without a terminal.

The journey: \`project\` (show, open or new — its pinecall.json names the gateway and the org it runs
in) → \`whoami\`, which is refused naming \`login\` when this machine is not signed in there → \`start\` holds
the agent while it is written, reloaded on every save → \`chat\` talks to it, \`test\` runs its
goldens, \`simulate\` plays a caller, \`remember\` runs its memory cases — on the copy \`start\` holds,
or with nothing held on whoever holds it: a terminal, a colleague, production's own process →
\`calls\` lists what happened and \`call\` reads one call's log whole → \`agent\`, \`voices\`,
\`lexicon\`, \`docs\` and \`memory\` tune it → \`deploy\` runs it on Pinecall → \`supervise\` watches a
live call and moves on it → \`console_url\` opens the console for the person.
\`studio\` is the way to an agent with no class: \`new\` → \`save\` its instructions, tools and data
collection → \`try\` each tool → \`chat\` with it by name → \`deploy\` it.
\`docs_search\` and \`get_doc\` read docs.pinecall.io: read a page whole before writing code from it.

Every tool acts in the sandbox, and in production when asked with \`prod: true\`; the org's own
switch still decides whether the key may.

A tool that runs long (\`login\`, \`test\`, \`simulate\`, \`deploy\`) answers within \`wait_s\` seconds
(25 unless asked, at most 50) with what it has, and says how to keep waiting.

No secret passes through you: no tool takes a vendor key, a carrier secret or an app's secret, and
none returns a Pinecall key. A person types those in a terminal (\`pinecall providers add\`,
\`pinecall carriers add\`, \`pinecall secrets set\`) or in the console.

What cannot be undone is not a tool: erasing data, forgetting a contact, dropping a base, a number
or a carrier, removing a deployed app. Those stay \`pinecall\` verbs a person types.`;

/** The instructions a host gives the model: the journey, then each stage's tools by name. */
export function instructions(stages: readonly Stage[]): string {
  return [JOURNEY, "", "## The tools, by stage", "", ...stages.map((one) => `- **${one.stage}**: ${one.tools.map((tool) => `\`${tool.name}\``).join(", ")}`)].join("\n");
}
