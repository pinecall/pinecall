/** `pinecall login | whoami | secrets | team`: this machine signed in to one of your orgs, who the key is, the org's secrets and people. */

import type { Command } from "@commander-js/extra-typings";

import { connectionLine, type Context } from "../context.js";
import { UsageError } from "../errors.js";
import { openInBrowser } from "../kit/browser.js";
import { allOf, typedInSilence } from "../kit/stdin.js";
import { CLOUD_URL } from "../project/credentials.js";
import * as render from "./render.js";
import * as service from "./service/index.js";

const LOGIN = `
Prints a link and opens it. You sign in there — in a browser, where a password belongs — and
the page hands this terminal a key of its OWN, minted for you and labelled as this machine, so
it is revoked on its own from the console's API keys. Nothing types a password into a shell. Once per machine and
gateway: every verb on this machine runs on it.

A project says which org it runs in, in the pinecall.json \`pinecall new\` writes at its root, and
this machine's key in that org is made the first time a verb needs it — the person may belong to
many orgs. Outside a project, a verb acts in the org the sign-in's own key is in, and its first
line says which.

With no URL it is ${CLOUD_URL}, and it says so before anything is kept. A runtime on this
machine (\`pinecall-runtime setup\`) signs this machine in by itself. A server signs in nowhere: a
server's token from the console's API keys, in its secrets as PINECALL_KEY, which wins over any sign-in.

Examples
  $ pinecall login https://pinecall.example.com
  open this to sign in:
  https://pinecall.example.com/cli?c=cli_…

  waiting…
  signed in to https://pinecall.example.com as Ana García · org clinica
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

const TEAM = `
An admin of the org sets anyone's password, theirs included: typed twice without echo, or piped
(\`printf %s "$NEW" | pinecall team password ana@clinica.com\`), never a flag the shell would keep.
An invited person given a password is active at once, with no link opened. \`reset\` makes a
one-use link instead, for the person to choose their own; the gateway hands it over when the box
sends no mail, and mails it otherwise.

Examples
  $ pinecall team
  EMAIL              NAME  ROLE   STATUS  RUNS THE BOX
  ana@clinica.com    Ana   admin  active  yes
  $ pinecall team password luis@clinica.com
  password:
  again:
  luis@clinica.com signs in with the password typed, from their next sign-in · active
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
    .description("sign this machine in to a gateway through a browser: every verb on it runs on that sign-in")
    .argument("[gateway]", `the gateway to sign in to; ${CLOUD_URL} when left out`)
    .option("--no-open", "print the link and do not open a browser")
    .addHelpText("after", LOGIN)
    .action(async (gateway, flags) => {
      if (gateway === undefined) ctx.io.info(render.DEFAULT_GATEWAY(CLOUD_URL));
      const signed = await signInThrough(ctx, gateway ?? CLOUD_URL, flags.open);
      const machine = service.machineSignIn(ctx, signed.gateway)!;
      ctx.io.result({ ...signed, advice: await service.adviceAt(machine.url, machine.key) }, render.loggedIn);
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

  const team = program
    .command("team")
    .description("the org's people: listed, a password set for one, or a one-use link to choose it")
    .addHelpText("after", TEAM);
  team
    .command("list", { isDefault: true })
    .description("every person of the org: address, name, role, whether they are active")
    .action(async () => ctx.io.result(await service.listTeam(ctx), render.team));
  team
    .command("password")
    .description("set a person's password: typed twice without echo, or piped in; an invited person becomes active")
    .argument("<email>")
    .action(async (email) => {
      const password = ctx.io.interactive ? await typedTwice(ctx) : (await allOf()).replace(/\r?\n$/, "");
      ctx.io.result(await service.setTeamPassword(ctx, service.SetPasswordInput.parse({ email, password })), render.passwordSet);
    });
  team
    .command("reset")
    .description("a one-use link the person opens to choose their own password")
    .argument("<email>")
    .action(async (email) => ctx.io.result(await service.resetLink(ctx, email), render.resetLinkFor));
}

// The same password twice, or nothing is sent: a typo would lock the person out.
async function typedTwice(ctx: Context): Promise<string> {
  const first = await typedInSilence("password: ", ctx.io);
  const again = await typedInSilence("again: ", ctx.io);
  if (first !== again) throw new UsageError("the two passwords differ: nothing was set");
  return first;
}

// Browser sign-in, key verification and storage.
async function signInThrough(ctx: Context, gateway: string, open: boolean): Promise<service.SignedIn> {
  const signIn = await service.startSignIn(ctx, service.StartSignInInput.parse({ gateway }));
  for (const line of render.signInLink(signIn.link)) ctx.io.info(line);
  if (open) openInBrowser(signIn.link);
  return await signIn.done;
}
