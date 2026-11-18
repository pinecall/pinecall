/** `pinecall email layout`: the HTML the org's agents' emails are set in. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import * as render from "./render.js";
import * as service from "./service.js";

const LAYOUT = `
An agent answers an email in its own words, and they are set in the org's layout: an HTML file that
says {{content}} once, where the reply goes, and {{subject}} wherever the subject should show.
An org that keeps none has its replies set in a plain one, on white, in nobody's brand.

  $ pinecall email layout set acme.html
  $ pinecall email layout preview "Hola Ana,\\n\\n- **sábado** 10 a 14" --subject Horarios --out reply.html

The agent's words are read for paragraphs, lists (-), **bold**, *italics* and links; everything
else is text. The mailbox itself is a carrier account (\`pinecall carriers add email\`), and an
address is given to an agent with \`pinecall numbers import <address> --agent <slug> --channel email\`.
`;

export function register(program: Command, ctx: Context): void {
  const email = program.command("email").description("the HTML the org's agents' emails are set in");
  const layout = email.command("layout").description("show | set | preview | clear the org's email layout").addHelpText("after", LAYOUT);
  layout
    .command("show", { isDefault: true })
    .description("the layout the org's agents' emails are set in now")
    .action(async () => ctx.io.result(await service.showLayout(ctx), render.layout));
  layout
    .command("set")
    .description("keep an HTML file as the org's layout")
    .argument("<file>", "an HTML file that says {{content}} once")
    .action(async (file) => ctx.io.result(await service.setLayout(ctx, file), render.layout));
  layout
    .command("preview")
    .description("words set in the layout as a reply would be; nothing is sent")
    .argument("<words>", "what the agent would write")
    .option("--subject <subject>", "the subject the reply answers")
    .option("--file <file>", "a layout to try before it is kept")
    .option("--out <file>", "where the HTML is written")
    .action(async (words, flags) => {
      const input = service.PreviewInput.parse({ text: words.replace(/\\n/g, "\n"), subject: flags.subject, file: flags.file, out: flags.out });
      ctx.io.result(await service.previewLayout(ctx, input), render.preview);
    });
  layout
    .command("clear")
    .description("forget the org's layout, back to the plain one")
    .action(async () => ctx.io.result(await service.clearLayout(ctx), render.cleared));
}
