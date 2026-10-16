/** `pinecall login | link | whoami | secrets`: this machine signed in, the project tied to an org, who the key is, the org's secrets. */

import type { Command } from "@commander-js/extra-typings";

import { connectionLine, type Context } from "../context.js";
import { UsageError } from "../errors.js";
import { openInBrowser } from "../kit/browser.js";
import { allOf, readLine, typedInSilence } from "../kit/stdin.js";
import { CLOUD_URL } from "../project/credentials.js";
import * as render from "./render.js";
import * as service from "./service/index.js";

const LOGIN = `
Prints a link and opens it. You sign in there — in a browser, where a password belongs — and
the page hands this terminal a key of its OWN, minted for you and labelled as this machine, so
it is revoked on its own from Tokens. Nothing types a password into a shell, and the day your
org signs in with Google this verb does not change.

With no URL it is ${CLOUD_URL}, and it says so before anything is kept.

The key is the machine's sign-in, kept in ~/.pinecall/session.json (0600; PINECALL_HOME moves
it), and no verb runs on it: a project runs on the key \`pinecall link\` writes into its own
.env. \`link\` signs the machine in itself when it is not, so this is rarely typed. A server has
no login at all: a server's token from Tokens, in its secrets as PINECALL_KEY.

Examples
  $ pinecall login
  gateway  https://cloud.pinecall.io   (the default — \`pinecall login <url>\` for your own)

  open this to sign in:
  https://cloud.pinecall.io/cli?c=cli_…

  waiting…
  signed in to https://cloud.pinecall.io as Ana García
`;

const LINK = `
Run in the project's folder. Signs this machine in through a browser when it is not, asks
which of your orgs this project is — --org names it — and writes your key for that org into
./.env as PINECALL_KEY (and PINECALL_URL when the gateway is not ${CLOUD_URL}). Every verb run
in this folder, or under it, reads it from there: a project of another org is another folder
with its own .env, and nothing is ever switched.

The key is yours: your role decides what it may do, and --prod reaches production while your
org lets you act there. A server does not link: a server's token from Tokens, in its secrets.

Examples
  ~/clinica $ pinecall link --org clinica
  ▸ clinica · PINECALL_KEY written to .env
  git would commit .env: add it to .gitignore before a commit carries your key
`;

const WHOAMI = `
Prints the one gateway every verb talks to — PINECALL_URL, with the key from the environment or
the project's .env — and what the gateway says the key is in the env asked: the org, the
key's id, the env, the label it was issued under, and whether you may act in production.
Then which envs the key opens there: a person's key opens the sandbox without --prod and
production with it, while their production switch is on; a server's token opens the one env
its prefix names. The key itself is neither printed nor sent anywhere else.

Examples
  $ pinecall whoami
  gateway https://cloud.pinecall.io · key from .env · sandbox
    org clinica · key k_4f2a1d9c66b30e17 · sandbox · ana-macbook · production: yes
    a person's key: the sandbox without --prod, production with it
`;

const SECRETS = `
A secret is the org's, per env: every app \`pinecall deploy\` put on Pinecall starts with all of
them. They are kept sealed, and nothing reads a value back — set, replace or drop. A change is a
new start of every app of the org in that env, the old process answering until the new one
registers. The value never goes on the command line, where the shell would keep it: it is typed
without echo, or piped (\`printf %s "$CRM_TOKEN" | pinecall secrets set CRM_TOKEN\`).

Examples
  $ printf %s "$CRM_TOKEN" | pinecall secrets set CRM_TOKEN --prod
  CRM_TOKEN kept · the org's hosted apps here start again with it
  $ pinecall secrets --prod
  NAME       SET               BY
  CRM_TOKEN  2026-09-30 13:22  m_ana
`;

export function register(program: Command, ctx: Context): void {
  program
    .command("login")
    .description("sign this machine in through a browser; `link` asks for it when it is needed")
    .argument("[gateway]", `the gateway to sign in to; ${CLOUD_URL} when left out`)
    .option("--no-open", "print the link and do not open a browser")
    .addHelpText("after", LOGIN)
    .action(async (gateway, flags) => {
      if (gateway === undefined) ctx.io.info(render.DEFAULT_GATEWAY(CLOUD_URL));
      const signed = await signInThrough(ctx, gateway ?? CLOUD_URL, flags.open);
      ctx.io.result(signed, render.signedIn);
    });

  program
    .command("link")
    .description("this project's folder to one of your orgs: your key, in its .env")
    .option("--org <slug>", "which org, when you belong to several and do not want to be asked")
    .option("--gateway <url>", "another gateway than the one this machine last signed in to")
    .option("--no-open", "when signing in: print the link and do not open a browser")
    .addHelpText("after", LINK)
    .action(async (flags) => {
      const input = service.LinkInput.parse({ org: flags.org, gateway: flags.gateway });
      let machine = service.machineSignIn(ctx, input.gateway);
      if (machine === undefined) {
        const signed = await signInThrough(ctx, input.gateway ?? CLOUD_URL, flags.open);
        ctx.io.info(render.signedIn(signed));
        machine = service.machineSignIn(ctx, signed.gateway)!;
      }
      const orgs = await service.listOrgs(ctx, machine);
      const org = input.org === undefined && orgs.length > 1 ? await askWhichOrg(ctx, orgs) : service.chooseOrg(orgs, input.org);
      const linked = await service.linkProject(ctx, machine, org);
      ctx.io.result(linked, render.linked);
      // Warn on every run until .env is git-ignored, so the key is never committed.
      if (!linked.gitIgnored) ctx.io.warn(render.GIT_WOULD_COMMIT);
    });

  program
    .command("whoami")
    .description("which org and which key this terminal is holding, and which envs it opens")
    .addHelpText("after", WHOAMI)
    .action(async () => {
      const who = await service.getWhoami(ctx);
      ctx.io.result(who, (one) => render.whoami(connectionLine(ctx), one));
    });

  const secrets = program
    .command("secrets")
    .description("the org's secrets: what its hosted apps are started with, as environment variables")
    .addHelpText("after", SECRETS);
  secrets
    .command("list", { isDefault: true })
    .description("the secrets' names, who set each and when")
    .action(async () => ctx.io.result(await service.listSecrets(ctx), render.secrets));
  secrets
    .command("set")
    .description("keep one; the same name again replaces it. The value typed without echo, or piped in")
    .argument("<NAME>", "capitals, digits and underscores, never starting with PINECALL_")
    .action(async (name) => {
      service.checkSecretName(name);
      // The whole of a pipe, not a line: a value of several lines, a PEM key.
      const value = ctx.io.interactive ? await typedInSilence(`${name}: `, ctx.io) : await allOf();
      ctx.io.result(await service.setSecret(ctx, service.SetSecretInput.parse({ name, value })), render.secretKept);
    });
  secrets
    .command("rm")
    .description("the secret dropped")
    .argument("<NAME>")
    .action(async (name) => ctx.io.result(await service.removeSecret(ctx, name), render.secretDropped));
}

// Browser sign-in, key verification and storage; shared by `login` and `link`.
async function signInThrough(ctx: Context, gateway: string, open: boolean): Promise<service.SignedIn> {
  const signIn = await service.startSignIn(ctx, service.StartSignInInput.parse({ gateway }));
  for (const line of render.signInLink(signIn.link)) ctx.io.info(line);
  if (open) openInBrowser(signIn.link);
  return await signIn.done;
}

// A numbered list on the terminal; without a person at it, the slugs are named and the verb refuses.
async function askWhichOrg(ctx: Context, orgs: service.Org[]): Promise<service.Org> {
  const slugs = orgs.map(service.slugOf);
  if (!ctx.io.interactive) throw new UsageError(`which org is this project? --org ${slugs.join(" | ")}`);
  for (const line of render.orgChoices(slugs)) ctx.io.info(line);
  const answer = (await readLine("which org is this project? ", ctx.io)).trim();
  const picked = slugs[Number(answer) - 1] ?? slugs.find((slug) => slug === answer);
  return service.chooseOrg(orgs, picked);
}
