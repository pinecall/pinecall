/** Accounts as a terminal reads them: the sign-in link, who signed in, what `link` wrote, who a key is, the secrets and the people. */

import { date, yesNo } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { Linked, MemberRow, ResetLink, SecretList, SignedIn, Whoami } from "./service/index.js";

/** Said before the link when no gateway was named, so the assumption is seen before anything is kept. */
export const DEFAULT_GATEWAY = (url: string): string => `gateway  ${url}   (the default — \`pinecall login <url>\` for your own)`;

export const GIT_WOULD_COMMIT = "git would commit .env: add it to .gitignore before a commit carries your key";

export const NO_SECRETS = "the org has no secrets here yet: `pinecall secrets set <NAME>`";

/** The lines around the link a person opens to sign in. */
export function signInLink(link: string): string[] {
  return ["", "open this to sign in:", link, "", "waiting…"];
}

export function signedIn(signed: SignedIn): string {
  return `signed in to ${signed.gateway} as ${signed.name}`;
}

/** The orgs as a numbered list, for the terminal's question. */
export function orgChoices(slugs: string[]): string[] {
  return slugs.map((slug, at) => `  ${at + 1}. ${slug}`);
}

export function linked(done: Linked): string {
  return `▸ ${done.org} · ${done.written.join(" and ")} written to .env`;
}

/** The connection line, then who the key is there and which envs it opens, indented under it. */
export function whoami(connection: string, who: Whoami): string[] {
  return [connection, `  ${describe(who)}`, `  ${envsOf(who)}`];
}

/** One line: org, key id, env, label, production access. A key without a label skips it rather than dangling a separator. */
export function describe(who: Whoami): string {
  const said = [`org ${who.slug ?? who.org}`, `key ${who.key_id}`, who.env];
  if (who.label !== null) said.push(who.label);
  said.push(`production: ${yesNo(who.production)}`);
  return said.join(" · ");
}

/** Which envs the key opens at this gateway: a server's token its own, a person's by their switch. */
export function envsOf(who: Whoami): string {
  if (who.name === undefined || who.name === null) {
    const token = who.env === "production" ? "production" : "sandbox";
    return `a ${token} server's token: that environment alone${token === "production" ? ", with --prod" : ""}`;
  }
  if (who.production) return "a person's key: the sandbox without --prod, production with it";
  return "a person's key: the sandbox; production is refused until an admin turns your switch on in Team";
}

export function secrets(found: SecretList): string[] {
  if (found.secrets.length === 0) return [NO_SECRETS];
  return table(
    ["name", "set", "by"],
    found.secrets.map((secret) => [secret.name, date(secret.set_at), secret.set_by]),
  );
}

export function secretKept({ name }: { name: string }): string {
  return `${name} kept · the org's hosted apps here start again with it`;
}

export function secretDropped({ name }: { name: string }): string {
  return `${name} dropped`;
}

export function team(people: MemberRow[]): string[] {
  return table(
    ["email", "name", "role", "status", "runs the box"],
    people.map((one) => [one.email, one.name, one.role, one.status, yesNo(one.operator)]),
  );
}

export function passwordSet(member: MemberRow): string {
  return `${member.email} signs in with the password typed, from their next sign-in · ${member.status}`;
}

export function resetLinkFor(reset: ResetLink): string[] {
  if (reset.link !== null) return [`${reset.email} chooses their password here, once:`, reset.link];
  return [reset.mailed ? `${reset.email} was mailed a one-use link to choose their password` : `no link was handed over for ${reset.email}: the box sends no mail, so set it with \`pinecall team password ${reset.email}\``];
}
