/** The dataset endpoints: the org's cases, the groups they fall into, the golden a call makes, and an agent's personas. */

import { seg, type GatewayClient } from "./client.js";

/** Where a case stands: kept at hang-up `pending`, then approved into the nightly or dismissed. */
export type CaseStatus = "pending" | "approved" | "dismissed";

/** A judge that broke on the call a case was kept from, and why. */
export interface BrokeOn {
  judge: string;
  reason: string;
}

/** One case: the golden a real call made, whose, from where, by whom, and what a person decided. */
export interface EvalCase {
  id: string;
  agent: string;
  name: string;
  golden: GoldenShape;
  /** The call the case was kept from; null for a case a person wrote by hand. */
  source_call: string | null;
  source_env: "sandbox" | "production";
  held_out: boolean;
  author: string;
  created_at: number;
  status: CaseStatus;
  broke: BrokeOn[];
  source_version: number | null;
  kept_in_repo: boolean;
  decided_by: string | null;
  group?: string | null;
  source?: "call" | "simulation" | "person";
  persona?: string | null;
}

/** A golden as the gateway carries it; the CLI's own type is `evals/service/goldens.ts`'s `Golden`. */
export interface GoldenShape {
  name: string;
  turns: { say?: string; event?: { name: string; data?: Record<string, unknown> }; then?: unknown[] }[];
  state?: Record<string, unknown>;
  memory?: string[];
  today?: string;
  expect?: Record<string, unknown>;
  promoted_from?: string;
}

/** A case as the gateway sends it: a field left at its default may be absent. */
export type SentCase = Omit<EvalCase, "status" | "broke" | "source_version" | "kept_in_repo" | "decided_by"> & Partial<EvalCase>;

/** The inbox: the agent's cases, and how many wait of how many may. */
export interface SentCaseList {
  cases: SentCase[];
  pending?: number;
  pending_at_most?: number;
}

/** What a person decided of one case; each field set is written. */
export interface CaseDecision {
  status?: CaseStatus;
  held_out?: boolean;
  kept_in_repo?: boolean;
  judge_was_wrong?: string;
  note?: string;
}

/** A diagnosis: the cause the calls share, and the change it proposes. */
export interface Proposal {
  cause: string;
  kind: "setting" | "code" | "knowledge" | "none";
  where: string;
  change: unknown;
  confidence: number;
}

/** Cases one judge broke on for one agent. */
export interface CaseGroup {
  id: string;
  agent: string;
  judge: string;
  cause: string;
  status: CaseStatus;
  since: number;
  cases: number;
  simulations: number;
  proposal?: Proposal | null;
  proposed_at?: number | null;
}

/** What a person decided of a whole group. */
export interface GroupDecision {
  status: "approved" | "dismissed";
  judge_was_wrong?: boolean;
  note?: string;
}

/** How a simulated caller acts on a spoken line, beside what it says. */
export interface Behavior {
  interrupts: number;
  pause_s: number;
  interferer_db: number | null;
  packet_loss: number;
  backchannels: number;
  speed: number;
  ambience: string;
}

/** A persona as the agent's list carries it: Pinecall's or the agent's own. */
export interface Persona {
  name: string;
  /** "pinecall" for the library's, "class" for the agent's class's, else the agent's slug. */
  owner: string;
  on: boolean;
  /** True on a row the agent's class declares, its switch of a library persona or its own: no door writes it. */
  fixed?: boolean;
  about: string;
  goal: string;
  style: string;
  facts: Record<string, string>;
  state: Record<string, unknown>;
  llm: string | null;
  tts: string | null;
  voice: string | null;
  expects: string[];
  tags: string[];
  behavior: Behavior;
  summary?: string | null;
  author?: string | null;
  set_at?: number | null;
}

/** Body of a persona write; `was` is the old name on a rename, `on` alone switches Pinecall's. */
export interface PersonaWrite {
  about?: string;
  goal?: string;
  style?: string;
  facts?: Record<string, string>;
  state?: Record<string, unknown>;
  llm?: string | null;
  tts?: string | null;
  voice?: string | null;
  expects?: string[];
  tags?: string[];
  behavior?: Partial<Behavior>;
  was?: string;
  on?: boolean;
}

/** A caller written for the agent, saved nowhere until it is written. */
export type ProposedPersona = Pick<Persona, "name" | "about" | "goal" | "style" | "facts" | "expects" | "tags" | "behavior">;

/** The callers written, and what they cost. */
export interface GeneratedPersonas {
  personas: ProposedPersona[];
  evals: number;
  cost_usd: number;
}

const caseDoor = (id: string): string => `/v1/evals/cases/${seg(id)}`;
const groupDoor = (id: string): string => `/v1/evals/groups/${seg(id)}`;
const personasDoor = (agent: string, name?: string): string => `/v1/agents/${seg(agent)}/personas${name === undefined ? "" : `/${seg(name)}`}`;

export function listCases(gw: GatewayClient, agent: string, status?: CaseStatus): Promise<SentCaseList> {
  return gw.get<SentCaseList>("/v1/evals/cases", { agent, status });
}

export function patchCase(gw: GatewayClient, id: string, decision: CaseDecision): Promise<SentCase> {
  return gw.patch<SentCase>(caseDoor(id), decision);
}

/** A golden written by hand kept as an approved case of the agent (`source: "person"`); the same name again rewrites it, a name a call made is a 409. */
export function writeCase(gw: GatewayClient, agent: string, name: string, body: { golden: GoldenShape; held_out?: boolean }): Promise<SentCase> {
  return gw.put<SentCase>(`/v1/agents/${seg(agent)}/cases/${seg(name)}`, body);
}

/** A finished call kept as an approved case; an expect left out is the one its broken verdicts give. */
export function createCase(gw: GatewayClient, body: { call: string; name: string; expect?: Record<string, unknown>; held_out?: boolean }): Promise<SentCase> {
  return gw.post<SentCase>("/v1/evals/cases", body);
}

export async function deleteCase(gw: GatewayClient, id: string): Promise<void> {
  await gw.delete(caseDoor(id));
}

/** The golden a finished call makes from a seq on, its expect derived from its broken verdicts; kept nowhere. */
export function getCallGolden(gw: GatewayClient, call: string, cut: { name?: string | undefined; fromSeq: number }): Promise<GoldenShape> {
  return gw.get<GoldenShape>(`/v1/calls/${seg(call)}/golden`, { from_seq: cut.fromSeq, name: cut.name });
}

export async function listGroups(gw: GatewayClient, agent: string): Promise<CaseGroup[]> {
  return (await gw.get<{ groups: CaseGroup[] }>("/v1/evals/groups", { agent })).groups;
}

export function getGroup(gw: GatewayClient, id: string): Promise<{ group: CaseGroup; cases: SentCase[] }> {
  return gw.get<{ group: CaseGroup; cases: SentCase[] }>(groupDoor(id));
}

/** The group diagnosed on the judge model: one eval, none on the org's own key. */
export function proposeGroup(gw: GatewayClient, id: string): Promise<CaseGroup> {
  return gw.post<CaseGroup>(`${groupDoor(id)}/propose`);
}

/** A proposed setting written as a new version of the key's corner; the settings answer. */
export function applyGroup(gw: GatewayClient, id: string): Promise<Record<string, unknown>> {
  return gw.post<Record<string, unknown>>(`${groupDoor(id)}/apply`);
}

/** A persona like the group's newest caller, kept as the agent's own. */
export function personaOfGroup(gw: GatewayClient, id: string): Promise<GeneratedPersonas> {
  return gw.post<GeneratedPersonas>(`${groupDoor(id)}/persona`);
}

export function patchGroup(gw: GatewayClient, id: string, decision: GroupDecision): Promise<CaseGroup> {
  return gw.patch<CaseGroup>(groupDoor(id), decision);
}

export async function listPersonas(gw: GatewayClient, agent: string): Promise<Persona[]> {
  return (await gw.get<{ personas: Persona[] }>(personasDoor(agent))).personas;
}

/** Create, replace, rename or switch one of the agent's personas; the agent's list after. */
export async function putPersona(gw: GatewayClient, agent: string, name: string, body: PersonaWrite): Promise<Persona[]> {
  return (await gw.put<{ personas: Persona[] }>(personasDoor(agent, name), body)).personas;
}

export async function deletePersona(gw: GatewayClient, agent: string, name: string): Promise<Persona[]> {
  return (await gw.delete<{ personas: Persona[] }>(personasDoor(agent, name))).personas;
}

/** Callers written for the agent by the judge model, saved nowhere. */
export function generatePersonas(gw: GatewayClient, agent: string, body: { n?: number; about?: string; from_call?: string; template?: string }): Promise<GeneratedPersonas> {
  return gw.post<GeneratedPersonas>(`${personasDoor(agent)}/generate`, body);
}
