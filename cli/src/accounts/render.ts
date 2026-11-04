/** Accounts as a terminal reads them: the sign-in link, who signed in and in which org, who a key is, the secrets and the people. */

import { date, formatNotice, yesNo } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { Advice, MemberRow, ResetLink, SecretList, SignedIn, Whoami } from "./service/index.js";

/** Said before the link when no gateway was named, so the assumption is seen before anything is kept. */
export const DEFAULT_GATEWAY = (url: string): string => `gateway  ${url}   (the default — \`pinecall login <url>\` for your own)`;

export const NO_SECRETS = "the org has no secrets here yet: `pinecall secrets set <NAME>`";

/** The lines around the link a person opens to sign in. */
export function signInLink(link: string): string[] {
  return ["", "open this to sign in:", link, "", "waiting…"];
}

/** What `login` did, and what the gateway serves or lends to this org, a stage at a time. */
export function loggedIn(done: SignedIn & { advice: Advice | null }): string[] {
  const lines = [`signed in to ${done.gateway} as ${done.name} · org ${done.org}`];
  if (done.advice === null || done.advice.stages.length === 0) return lines;
  lines.push("", "what this runtime gives your agents");
  const width = Math.max(...done.advice.stages.map((one) => one.choice.length)) + 2;
  for (const one of done.advice.stages) lines.push(`  ${(STAGES[one.stage] ?? one.stage).padEnd(10)}${one.choice.padEnd(width)}${one.runs_on}`);
  if (done.advice.stages.some((one) => one.runs_on === "needs a key")) lines.push("", "a stage that needs a key: pinecall providers add <vendor>");
  return lines;
}

const STAGES: Record<string, string> = { stt: "ears", llm: "thinking", tts: "voice" };

/** Where (gateway, org, env) on one line; the key, where it was read from, and what it opens, a label a line. */
export function whoami(where: { url: string; source: string }, who: Whoami): string[] {
  return [
    `${hostOf(where.url)} · org ${who.slug ?? who.org} · ${who.env}`,
    `  key   ${[who.key_id, ...(who.label === null ? [] : [who.label])].join(" · ")}`,
    `  from  ${where.source}`,
    `  opens ${envsOf(who)}`,
  ];
}

/** The key's line: its id, where it was read from, and the label it was issued under when it has one. */
export function describe(who: Whoami, source: string): string {
  const said = [`key ${who.key_id} from ${source}`];
  if (who.label !== null) said.push(who.label);
  return said.join(" · ");
}

// `https://cloud.pinecall.io` as a person names it; any other scheme or a port stays whole.
function hostOf(url: string): string {
  return url.replace(/^https:\/\//, "").replace(/\/$/, "");
}

/** Which envs the key opens at this gateway: a server's token its own, a person's by their switch. */
export function envsOf(who: Whoami): string {
  if (who.name === undefined || who.name === null) {
    const token = who.env === "production" ? "production" : "sandbox";
    return `the ${token} alone${token === "production" ? ", with --prod" : ""}: a server's token`;
  }
  if (who.production) return "the sandbox, and production with --prod: a person's key";
  return "the sandbox: production waits on an admin turning your switch on in Team";
}

export function secrets(found: SecretList): string[] {
  if (found.secrets.length === 0) return formatNotice(NO_SECRETS);
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
  return reset.mailed ? [`${reset.email} was mailed a one-use link to choose their password`] : formatNotice(`no link was handed over for ${reset.email}, the box sends no mail: \`pinecall team password ${reset.email}\` sets it`);
}
