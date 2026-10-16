/** `pinecall mcp install`: Pinecall written into every assistant on this machine, listed, or taken out — and what was done, line by line. */

import { errorMessage } from "../../errors.js";
import { registered, writeEntry } from "./configs.js";
import { entryFor, hosts, installed, type Host } from "./hosts.js";

/** What happened to one assistant. */
export interface Done {
  host: Host;
  did: "added" | "replaced" | "removed" | "not installed" | "not there" | "failed";
  why?: string;
}

/** One assistant as `--list` says it. */
export interface Listed {
  host: Host;
  state: "registered" | "not registered" | "not installed";
}

/** Write (or remove) Pinecall's entry in every installed assistant; an absent one is skipped, a broken file reported. */
export function installEverywhere(remove: boolean, home?: string): Done[] {
  return hosts(home).map((host): Done => {
    if (!installed(host)) return { host, did: "not installed" };
    const was = registered(host);
    if (remove && !was) return { host, did: "not there" };
    try {
      writeEntry(host, remove ? null : entryFor(host));
      return { host, did: remove ? "removed" : was ? "replaced" : "added" };
    } catch (failed) {
      return { host, did: "failed", why: errorMessage(failed) };
    }
  });
}

/** Every assistant, whether it is installed, and whether Pinecall is in it; changes nothing. */
export function listHosts(home?: string): Listed[] {
  return hosts(home).map((host) => ({ host, state: registered(host) ? "registered" : installed(host) ? "not registered" : "not installed" }));
}

/** The list, one line per assistant. */
export function renderListed(listed: Listed[]): string[] {
  return ["assistants on this machine:", ...listed.map((one) => `  ${one.host.label.padEnd(15)} ${one.state.padEnd(15)} ${one.host.file}`)];
}

/** The report: a line per assistant, and the two things that are not obvious. */
export function renderDone(done: Done[], remove: boolean): string[] {
  const lines = done.map((one) => `  ${one.did === "failed" ? "✗" : "·"} ${one.host.label.padEnd(15)} ${one.did.padEnd(14)} ${one.why ?? one.host.file}`);
  const touched = done.some((one) => one.did === "added" || one.did === "replaced");
  if (!touched || remove) return lines;
  return [
    ...lines,
    "",
    "  each file was copied beside itself as .bak first",
    "  restart the assistant: it read its config when it started",
    "  no key was written anywhere: the server reads the project's .env, and `login` signs this machine in",
  ];
}
