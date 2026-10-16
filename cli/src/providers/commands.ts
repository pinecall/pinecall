/** `pinecall providers`: every vendor this build runs, and the provider keys this org brought of its own. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { UsageError } from "../errors.js";
import { secretReader } from "../kit/stdin.js";
import * as render from "./render.js";
import * as service from "./service.js";

const PROVIDERS = `
With nothing after it: every vendor this build runs — what each does, every other word it
answers to, and the one word for what it is still waiting for on this box. \`ready\` is the only
one that runs a call; \`no plugin\` and \`no key\` are the operator's to fix, and \`its own\` is a
vendor whose credentials are a chain or a pair and never one key anybody could bring.

A key added here is this org's own account with that vendor, and every call of this org runs
on it from the next one; a vendor nobody brought runs on the deployment's key when it lends that
vendor (\`pinecall limits\` says which), and is refused when it does not. add reads the
key from stdin — typed with nothing echoed on a terminal, one piped line off one — and never
from a flag: argv is visible in \`ps\` to every user on the machine, and a key pasted as an argument
is a key in the shell history. rm gives that vendor back to the deployment's key, where it lends one.

No endpoint a person reads ever answers with a provider key: list prints the vendors and nothing
else, not a value, not a prefix, not a fingerprint. The one endpoint that does read a key back is
the worker's — GET /v1/agents/<slug>/provider-keys, an org's own keys to an org's own process,
on that org's key — and it is the whole reason the vault exists. A key that was lost is set
again.

Examples
  $ pinecall providers --does tts
  VENDOR        DOES         STANDING   VARIABLE              ALSO KNOWN AS
  livekit       llm,stt,tts  ready                            inference lk
  cartesia      stt,tts      no key     CARTESIA_API_KEY
  elevenlabs    stt,tts      ready      ELEVEN_API_KEY        11labs eleven elevenlab
  rime          tts          no key     RIME_API_KEY
  speechmatics  stt,tts      no plugin  SPEECHMATICS_API_KEY
`;

export function register(program: Command, ctx: Context): void {
  const providers = program
    .command("providers")
    .description("every vendor this build runs, and the provider keys this org brought of its own")
    .addHelpText("after", PROVIDERS);
  providers
    .command("catalog", { isDefault: true })
    .description("every vendor this build runs: what each does, its standing, its variable, its other names")
    .option("--does <job>", `only the vendors that do one job: ${service.MODALITIES.join(" | ")}`)
    .action(async (flags) => {
      if (flags.does !== undefined && !(service.MODALITIES as readonly string[]).includes(flags.does)) {
        throw new UsageError(`no modality called ${flags.does}: ${service.MODALITIES.join(" | ")}`);
      }
      ctx.io.result(await service.listProviders(ctx, service.ListProvidersInput.parse({ does: flags.does })), render.catalog);
    });
  providers
    .command("add")
    .description("bring this org's own key for a vendor; the key on stdin, never on the command line")
    .argument("<vendor>", "the vendor's name, as the catalog lists it")
    .action(async (vendor) => {
      const key = await secretReader(ctx.io)(`${vendor} key`);
      ctx.io.result(await service.addProviderKey(ctx, service.AddProviderKeyInput.parse({ vendor, key })), render.providerKeyAdded);
    });
  providers
    .command("rm")
    .description("give a vendor back to the deployment's key, where it lends one")
    .argument("<vendor>")
    .action(async (vendor) => ctx.io.result(await service.removeProviderKey(ctx, vendor), render.providerKeyRemoved));
  providers
    .command("list")
    .description("only the vendors this org brought a key for, by name")
    .action(async () => ctx.io.result(await service.listProviderKeys(ctx), render.providerKeys));
}
