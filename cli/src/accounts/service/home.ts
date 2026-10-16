/** `~/.pinecall/session.json`: this machine's sign-in per gateway, and the phone it calls from. */

import { chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// Owner-only: other accounts on the machine can neither list the directory nor read the file.
const DIRECTORY_MODE = 0o700;
const FILE_MODE = 0o600;
const SESSION_FILE = "session.json";

/** The variable that moves the home folder away from `~/.pinecall`. */
export const HOME_VARIABLE = "PINECALL_HOME";

/** What this machine keeps for one gateway. */
export interface SignedGateway {
  /** The key from `pinecall login` on this gateway; `link` mints project keys from it. */
  key?: string;
  /**
   * The person's own phone number (`pinecall line from`), so a sandbox ring from it reaches their
   * agent. Re-sent by every `pinecall start`; the gateway does not persist it.
   */
  calling?: string;
}

/**
 * The machine's sign-in, one entry per gateway plus the last one used. A project's key lives in its
 * `.env`, never here; this lets `link` mint keys without the browser.
 */
export interface HomeFile {
  gateways: Record<string, SignedGateway>;
  last?: string;
}

/** The machine's sign-in at one gateway. */
export interface MachineSignIn {
  url: string;
  key: string;
}

/** The home folder: `PINECALL_HOME`, else `~/.pinecall`. */
export function homeOf(env: NodeJS.ProcessEnv): string {
  return env[HOME_VARIABLE] ?? join(homedir(), ".pinecall");
}

/** Read the file, or an empty one when there is none. */
export function readHome(home: string): HomeFile {
  try {
    const parsed = JSON.parse(readFileSync(join(home, SESSION_FILE), "utf8")) as Partial<HomeFile>;
    return { gateways: parsed.gateways ?? {}, ...(parsed.last === undefined ? {} : { last: parsed.last }) };
  } catch {
    return { gateways: {} };
  }
}

/** Keep the key for a gateway and make it the last one used. */
export function writeSignIn(home: string, url: string, key: string): void {
  const file = readHome(home);
  file.gateways[url] = { ...file.gateways[url], key };
  file.last = url;
  writeHome(home, file);
}

/** The signed-in gateway and key: the one named, else the last one used. */
export function readSignIn(home: string, url?: string): MachineSignIn | undefined {
  const file = readHome(home);
  const at = url ?? file.last;
  const key = at === undefined ? undefined : file.gateways[at]?.key;
  return at === undefined || key === undefined ? undefined : { url: at, key };
}

/** The phone number set by `pinecall line from` for this gateway. */
export function readCallerNumber(home: string, url: string): string | undefined {
  return readHome(home).gateways[url]?.calling;
}

/** Set or clear the caller phone number; a no-op for a gateway never signed in to. */
export function writeCallerNumber(home: string, url: string, number: string | undefined): void {
  const file = readHome(home);
  const signed = file.gateways[url];
  if (signed === undefined) return;
  const { calling: _was, ...rest } = signed;
  file.gateways[url] = number === undefined ? rest : { ...rest, calling: number };
  writeHome(home, file);
}

function writeHome(home: string, file: HomeFile): void {
  mkdirSync(home, { recursive: true, mode: DIRECTORY_MODE });
  const path = join(home, SESSION_FILE);
  writeFileSync(path, `${JSON.stringify(file, null, 2)}\n`, { mode: FILE_MODE });
  // writeFileSync's mode applies only on create.
  chmodSync(path, FILE_MODE);
}
