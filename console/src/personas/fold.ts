/** What the Personas page folds from the doors: one agent's roster, a persona's manner in a few words, and its newest simulation. */

import type { CallerBehavior } from "@pinecall/core/wire/rest-evals";
import { ago } from "../lib/format";
import { aboutOf, isPinecalls, standingOf, type Persona, type PersonaRun } from "../simulations/door";

/** What one agent answered: its callers (Pinecall's as it switched them, then its own) and its newest simulated calls. */
export interface Roster {
  agent: string;
  /** Null when the door refused; `refused` says why. */
  callers: Persona[] | null;
  /** One page, newest first; empty when that door refused. */
  runs: PersonaRun[];
  refused: string | null;
}

const ROOMS: Record<string, string> = { television: "Television", cafe: "Café", office: "Office", street: "Street" };

const share = (part: number): string => `${Math.round(part * 100)}%`;

/** How a persona behaves on a spoken line, a few words each; none for one that waits, answers at once and calls from a quiet room. */
export function tagsOf(acts: CallerBehavior): string[] {
  return [
    ...(acts.interrupts > 0 ? [`Interrupts ${share(acts.interrupts)}`] : []),
    ...(acts.pause_s > 0 ? [`Pauses ${acts.pause_s} s`] : []),
    ...(acts.interferer_db !== null ? [`${ROOMS[acts.ambience] ?? "Noise"} behind`] : []),
    ...(acts.packet_loss > 0 ? [`${share(acts.packet_loss)} loss`] : []),
    ...(acts.backchannels > 0 ? [`Murmurs ${share(acts.backchannels)}`] : []),
    ...(acts.speed !== 1 ? [`${acts.speed}× pace`] : []),
  ];
}

/** How a call went, in a few words. */
export function saidOf(run: PersonaRun): string {
  const standing = standingOf(run);
  if (standing === "live") return "on the line now";
  if (standing === "unjudged") return `not judged, ${ago(run.started_at)}`;
  return `${run.score?.held ?? 0} of ${run.score?.judged ?? 0} judges held, ${ago(run.started_at)}`;
}

/** What a persona is after, in a sentence: its own goal, or what Pinecall's is for. */
export const goalOf = (persona: Persona): string => (isPinecalls(persona) ? aboutOf(persona) : persona.goal);

const byName = (one: Persona, other: Persona): number => one.name.localeCompare(other.name);
const isRed = (persona: Persona): boolean => persona.tags.includes("red-team");

/** The agent's own personas, by name. */
export const ownOf = (callers: readonly Persona[]): Persona[] => callers.filter((one) => !isPinecalls(one)).sort(byName);

/** Pinecall's personas, the red team last, by name. */
export const libraryOf = (callers: readonly Persona[]): Persona[] => callers.filter(isPinecalls).sort((one, other) => Number(isRed(one)) - Number(isRed(other)) || byName(one, other));

/** Whether a persona answers a search: by its name, who it is or what it wants. */
export function matches(persona: Persona, typed: string): boolean {
  const asked = typed.trim().toLowerCase();
  return asked === "" || `${persona.name} ${persona.about} ${persona.goal} ${persona.summary ?? ""}`.toLowerCase().includes(asked);
}

// A persona's calls drawn beside it: the newest few.
const SHOWN = 5;

/** A persona's newest calls to one agent, among the page read; `runs` newest first. */
export const callsOf = (runs: readonly PersonaRun[], name: string): PersonaRun[] => runs.filter((run) => run.persona === name).slice(0, SHOWN);

/** A persona's newest calls to any of the agents read. */
export function newestCallsOf(rosters: Iterable<Roster>, name: string): PersonaRun[] {
  return [...rosters]
    .flatMap((roster) => callsOf(roster.runs, name))
    .sort((one, other) => (other.started_at ?? 0) - (one.started_at ?? 0))
    .slice(0, SHOWN);
}
