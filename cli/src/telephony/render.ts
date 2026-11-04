/** Telephony as a terminal reads it: the numbers, what the accounts own, a plan's steps, the carriers, the line, the callbacks. */

import type { Limit } from "../billing/service.js";
import { count, date, formatHint, formatNotice } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { AvailableNumbers, Callback, CallbackPage, Carrier, CarrierListed, NumberBought, NumberPlan, NumberRow, OwnedNumber, TheLine } from "./service.js";

export const NO_NUMBERS = "no number answers in this env: `pinecall numbers import <+34…> --agent <slug>`";
export const NO_CARRIERS = "the org holds no carrier account: `pinecall carriers add twilio --account-sid AC… --user SK…`";
export const SEVERAL_CARRIERS = "several accounts: `pinecall numbers import <+34…> --agent <slug> --account <id>` names one";
export const NOBODY_WAITING = "nobody is waiting for a call back";

/** The env's numbers as a table; the carrier account only when the org holds several, since one says nothing. */
export function numbers(rows: NumberRow[]): string[] {
  if (rows.length === 0) return formatNotice(NO_NUMBERS);
  const several = new Set(rows.flatMap((one) => (one.route.managed || one.account == null ? [] : [one.account]))).size > 1;
  return table(
    ["number", "channel", "agent", "env", several ? "account" : "how"],
    rows.map((one) => [one.route.number ?? "—", one.route.channel, one.route.agent, one.route.env, one.route.managed ? "bought here" : several ? (one.account ?? "—") : "imported"]),
  );
}

/** A number row: number, channel, agent, env, and whether it was bought here or whose account it is. */
export function numberLine(one: NumberRow): string {
  const said = [one.route.number ?? "—", one.route.channel, `→ ${one.route.agent}`, one.route.env];
  if (one.route.managed) said.push("bought here");
  else if (one.account !== undefined && one.account !== null) said.push(one.account);
  return said.join(" · ");
}

export function available(found: AvailableNumbers): string[] {
  if (found.numbers.length === 0) {
    return formatNotice(
      found.kind === "sip"
        ? "a SIP peer lists nothing here: `pinecall numbers import <+34…> --agent <slug>` takes its number as typed"
        : "the org's accounts own no number, buy one at the carrier: `pinecall numbers available` lists it then",
    );
  }
  const order = (one: OwnedNumber): number => (one.imported ? 0 : one.held_elsewhere ? 2 : 1);
  const sorted = [...found.numbers].sort((one, other) => order(one) - order(other));
  // A carrier names a number after itself, `(361) 733-4133`, until someone names it: only a real name is shown.
  const named = (one: OwnedNumber): string => (one.name === "" || /^[\d\s()+\-.]+$/.test(one.name) ? "—" : one.name);
  const labelled = sorted.some((one) => named(one) !== "—");
  const accounts = new Set(sorted.flatMap((one) => (one.account === undefined ? [] : [one.account])));
  const rows = table(
    ["number", ...(labelled ? ["name"] : []), ...(accounts.size > 1 ? ["account"] : []), "here"],
    sorted.map((one) => [one.number, ...(labelled ? [named(one)] : []), ...(accounts.size > 1 ? [one.account ?? "—"] : []), one.imported ? "routed here" : one.held_elsewhere ? "another org's" : "not routed here"]),
  );
  return [`${found.kind} · ${count(sorted.length, "number")}`, ...rows, formatHint("pinecall numbers import <number> --agent <slug> --dry-run checks one")];
}

/** An owned number: the number, its name at the carrier, the account, and whether this env routes it. */
export function ownedLine(one: OwnedNumber): string {
  const said = [one.number];
  if (one.name !== "" && one.name !== one.number) said.push(one.name);
  if (one.account !== undefined) said.push(one.account);
  said.push(one.imported ? "routed here" : one.held_elsewhere ? "held by another org" : "not routed here");
  return said.join(" · ");
}

export function imported(done: NumberPlan): string[] {
  const lines = done.steps.map((step) => `  ${step}`);
  if (done.dry_run) lines.push("  nothing written: drop --dry-run to do it");
  return lines;
}

export function bought(done: NumberBought): string[] {
  const lines = done.steps.map((step) => `  ${step}`);
  lines.push(`  ${boughtSoFar(done.stock)}`);
  if (done.dry_run) lines.push(`  nothing bought: drop --dry-run to buy ${done.route.number ?? "it"}`);
  return lines;
}

/** The `numbers` limit as a line: how many bought numbers the env holds, of how many. */
export function boughtSoFar(stock: Limit): string {
  const used = Math.round(stock.used);
  return stock.limit === null ? `bought numbers in this env: ${used}, no limit` : `bought numbers in this env: ${used} of ${stock.limit}`;
}

export function dropped({ number }: { number: string }): string {
  return `${number} answers nothing here now. Your carrier still owns it.`;
}

/** The org's carrier accounts as a table: the account (what `--account` takes), its kind, its label, its networks, its numbers here. */
export function carriers(rows: CarrierListed[]): string[] {
  if (rows.length === 0) return formatNotice(NO_CARRIERS);
  const networked = rows.some((row) => row.networks.length > 0);
  const labelled = rows.some((row) => row.label !== "");
  const lines = table(
    ["account", "kind", ...(labelled ? ["label"] : []), ...(networked ? ["networks"] : []), "numbers here"],
    rows.map((row) => [row.account, row.kind, ...(labelled ? [row.label || "—"] : []), ...(networked ? [row.networks.map((one) => `${one.network} ${one.state}`).join(", ") || "—"] : []), row.routed]),
  );
  if (rows.length > 1) lines.push(...formatNotice(SEVERAL_CARRIERS));
  return lines;
}

/** An account: its id, its kind, its label, a peer's networks with where each stands, and its numbers here. */
export function carrierLine(row: Carrier, routed?: number): string {
  const said = [row.account, row.kind];
  if (row.label !== "") said.push(row.label);
  if (row.networks.length > 0) said.push(row.networks.map((one) => `${one.network} ${one.state}`).join(", "));
  if (routed !== undefined) said.push(routed === 1 ? "1 number here" : `${routed} numbers here`);
  return said.join(" · ");
}

export function carrier(row: Carrier): string {
  return carrierLine(row);
}

export function carrierKept(kept: Carrier): string[] {
  const lines = [`kept: ${carrierLine(kept)}`];
  if (kept.networks.some((one) => one.state === "waiting")) lines.push("  each waiting network opens once Pinecall's operator approves it");
  lines.push(formatHint(...(kept.networks.some((one) => one.state === "waiting") ? ["pinecall carriers show says when"] : []), "pinecall numbers import <+34…> --agent <slug> routes one of its numbers"));
  return lines;
}

export function carrierDropped({ account }: { account: string | undefined }): string[] {
  return formatNotice(`${account ?? "the org's account"} forgotten, and its numbers stay routed until each is dropped: \`pinecall numbers drop <+34…>\``);
}

/** Where the line rings, and after a colon how to change it, as one sentence. Names people by email, never member id. */
export function lineSentence(said: TheLine): string {
  if (!said.held && said.waiting.length === 0) return `nobody is answering ${said.agent}: \`pinecall start\` answers here`;
  if (!said.held) return `nobody holds the line of ${said.agent} (running: ${said.waiting.map((one) => one.name ?? "the org's own key").join(", ")}), so a call from a number nobody said was theirs rings nowhere: \`pinecall line claim\` takes it`;
  // Routing by number takes precedence over holding the line.
  const mine = said.calling.length > 0 ? `your calls from ${said.calling.join(", ")}` : undefined;
  if (said.yours) {
    const also = [mine, whoElse(said)].filter((part) => part !== undefined);
    return ["rings in this terminal", ...also].join(" · ");
  }
  const theirs = `rings in ${whose(said)}`;
  if (mine !== undefined) return `${theirs}, but not ${mine}`;
  return `${theirs}: \`pinecall line from <+your-number>\` routes yours, \`pinecall line claim\` takes it`;
}

/** Where the line rings, then how to change it on a line of its own. */
export function line(said: TheLine): string[] {
  return formatNotice(lineSentence(said));
}

/** What a release says when nobody else was there to pick the line up. */
export function released(said: TheLine): string[] {
  if (said.held) return line(said);
  return formatNotice(`let go, and nobody else is running ${said.agent}, so a call from a number nobody said was theirs rings nowhere: \`pinecall line claim\` takes it`);
}

export function calling({ calling: numbers }: { calling: string[] }): string {
  return `calls from ${numbers.join(", ")} reach this terminal`;
}

export function callerForgotten({ forgot }: { forgot: string[] }): string {
  return forgot.length === 0 ? "no number was reaching this terminal" : `calls from ${forgot.join(", ")} no longer reach this terminal`;
}

export function callbacks(page: CallbackPage): string[] {
  if (page.requests.length === 0) return [NOBODY_WAITING];
  const lines = page.requests.map(callbackLine);
  if (page.next !== null) lines.push(formatHint(`--after ${page.next} reads on`));
  return lines;
}

/** One request as a line: time, agent, number, channel and source. */
export function callbackLine(one: Callback): string {
  const took = one.via === "overflow" ? `overflow on ${one.call ?? "?"}` : one.via === "agent" ? `the agent on ${one.call ?? "?"}` : "the widget";
  return `${date(one.ts)}  ${one.agent}  ${one.number}  ${one.channel}  via ${took}`;
}

function whose(said: TheLine): string {
  const name = said.holding?.name;
  return name === null || name === undefined ? "the terminal running the org's own key" : name;
}

function whoElse(said: TheLine): string | undefined {
  const names = said.waiting.map((one) => one.name ?? "the org's own key");
  return names.length === 0 ? undefined : `also running: ${names.join(", ")}`;
}
