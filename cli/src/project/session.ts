/** `~/.pinecall/session.json`: who this machine is at each gateway — the sign-in, the keys in the person's orgs — and the phone it calls from. */

import { chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// Owner-only: other accounts on the machine can neither list the directory nor read the file.
const DIRECTORY_MODE = 0o700;
const FILE_MODE = 0o600;

/** The file in the CLI's home. `pinecall-runtime setup` writes its own gateway's entry here too. */
export const SESSION_FILE = "session.json";
/** Where a runtime `pinecall-runtime setup` runs on this machine answers, as it signs the machine in. */
export const LOCAL_GATEWAY = "http://127.0.0.1:8080";

/**
 * What this machine keeps for one gateway. `key` is the sign-in — `pinecall login`'s, or the local
 * runtime admin's that `pinecall-runtime setup` writes — and `org` the org it acts in; `orgs` the
 * keys minted from it in the person's other orgs, each labelled as this machine at the gateway.
 */
export interface SignedGateway {
  key?: string;
  org?: string;
  orgs?: Record<string, string>;
  /**
   * The person's own phone number (`pinecall line from`), so a sandbox ring from it reaches their
   * agent. Re-sent by every `pinecall start`; the gateway does not persist it.
   */
  calling?: string;
}

/** The machine's sign-in, one entry per gateway, and the gateway signed in to last. */
export interface SessionFile {
  gateways: Record<string, SignedGateway>;
  last?: string;
}

/** The machine's sign-in at one gateway. */
export interface MachineSignIn {
  url: string;
  key: string;
  /** The org the sign-in's key acts in, when known. */
  org?: string;
}

/** Read the file, or an empty one when there is none. */
export function readSession(home: string): SessionFile {
  try {
    const parsed = JSON.parse(readFileSync(join(home, SESSION_FILE), "utf8")) as Partial<SessionFile>;
    return { gateways: parsed.gateways ?? {}, ...(parsed.last === undefined ? {} : { last: parsed.last }) };
  } catch {
    return { gateways: {} };
  }
}

/** Keep a sign-in at a gateway and make it the last one: the keys minted from an earlier one go with it. */
export function keepSignIn(home: string, url: string, key: string, org: string | undefined): void {
  const file = readSession(home);
  const { calling } = file.gateways[url] ?? {};
  file.gateways[url] = { key, ...(org === undefined ? {} : { org }), ...(calling === undefined ? {} : { calling }) };
  file.last = url;
  writeSession(home, file);
}

/** The sign-in at the gateway named, else at the last one. */
export function readSignIn(home: string, url?: string): MachineSignIn | undefined {
  const file = readSession(home);
  const gateway = url ?? file.last;
  const signed = gateway === undefined ? undefined : file.gateways[gateway];
  if (gateway === undefined || signed?.key === undefined) return undefined;
  return { url: gateway, key: signed.key, ...(signed.org === undefined ? {} : { org: signed.org }) };
}

/** This machine's key in an org at a gateway: the sign-in's when it is that org's, else one minted there. */
export function keyIn(home: string, url: string, org: string): string | undefined {
  const signed = readSession(home).gateways[url];
  if (signed?.key === undefined) return undefined;
  return signed.org === org ? signed.key : signed.orgs?.[org];
}

/** Keep a key minted in one of the person's orgs at a gateway signed in to. */
export function keepOrgKey(home: string, url: string, org: string, key: string): void {
  const file = readSession(home);
  const signed = file.gateways[url];
  if (signed === undefined) return;
  file.gateways[url] = { ...signed, orgs: { ...signed.orgs, [org]: key } };
  writeSession(home, file);
}

/** The phone number set by `pinecall line from` for this gateway. */
export function readCallerNumber(home: string, url: string): string | undefined {
  return readSession(home).gateways[url]?.calling;
}

/** Set or clear the caller phone number; a no-op for a gateway never signed in to. */
export function writeCallerNumber(home: string, url: string, number: string | undefined): void {
  const file = readSession(home);
  const signed = file.gateways[url];
  if (signed === undefined) return;
  const { calling: _was, ...rest } = signed;
  file.gateways[url] = number === undefined ? rest : { ...rest, calling: number };
  writeSession(home, file);
}

function writeSession(home: string, file: SessionFile): void {
  mkdirSync(home, { recursive: true, mode: DIRECTORY_MODE });
  const path = join(home, SESSION_FILE);
  writeFileSync(path, `${JSON.stringify(file, null, 2)}\n`, { mode: FILE_MODE });
  // writeFileSync's mode applies only on create.
  chmodSync(path, FILE_MODE);
}
