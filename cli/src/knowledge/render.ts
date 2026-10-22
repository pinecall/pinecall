/** Knowledge as a terminal reads it: a push, the bases, a score, an attachment, a contact's facts, the policy, an extraction run. */

import { BROKEN, date, HELD } from "../kit/format.js";
import type { BaseAttached, ContactFact, ContactRemembered, DocsPushed, DocsSkipped, ExtractionRun, Forgotten, KnowledgeList, KnowledgeScore, KnowledgeUses, MemoryScore, Policy } from "./service/index.js";

export const NO_BASES = "no base pushed yet: pinecall docs push sends agents/<name>/docs/ under the agent's slug";
export const NOTHING_ATTACHED = "no agent reads a base here: `pinecall docs attach <base>` gives one its base";

// Superseded facts are dimmed on a TTY.
const DIM = "\u001b[2m";
const PLAIN = "\u001b[0m";

/** A base whose files said no language clearly is stemmed in none: the line says how to say it. */
const NO_LANGUAGE = "no language counted from the files, so no stemming: say it with --language <code>";

/** One push per line: base, files, chunks, the language its words are stemmed in and time taken; an agent passed over says why. */
export function pushed(results: (DocsPushed | DocsSkipped)[]): string[] {
  return results.map((one) => {
    if ("skipped" in one) return `${one.agent} · ${one.skipped}`;
    const language = one.language === "simple" ? NO_LANGUAGE : one.language;
    return `${one.base} · ${one.files} files · ${one.chunks} chunks · ${language} · ${Math.round(one.took_ms)} ms`;
  });
}

export function bases(found: KnowledgeList): string[] {
  if (found.bases.length === 0) return [NO_BASES];
  return found.bases.map((base) => `${base.base} · ${base.chunks} chunks · ${base.language} · pushed ${date(base.pushed_at)}`);
}

export function dropped({ base }: { base: string }): string {
  return `dropped ${base}`;
}

/** Each score: a summary line, then one line per missed question; an agent passed over says why. */
export function scores(results: (KnowledgeScore | DocsSkipped)[]): string[] {
  return results.flatMap((one) => ("skipped" in one ? [`${one.agent} · ${one.skipped}`] : score(one)));
}

export function score(one: KnowledgeScore): string[] {
  const figures = `${one.base} · ${one.model} · ${one.questions} questions · recall@${one.k} ${one.recall_at_k.toFixed(2)} · nDCG@10 ${one.ndcg_at_10.toFixed(2)} · ${Math.round(one.took_ms)} ms`;
  return [figures, ...one.misses.map((missed) => `  missed: ${missed.asks} → wanted ${missed.expects.join(" or ")}, got ${missed.found[0] ?? "nothing"}`)];
}

export function attached(done: BaseAttached): string {
  return `${done.agent} · ${done.base} attached · ${cornerOf(done)}`;
}

export function detached(done: BaseAttached): string {
  return `${done.agent} · ${done.base} detached · ${cornerOf(done)}`;
}

export function attachments(uses: KnowledgeUses): string[] {
  if (uses.bases.length === 0) return [NOTHING_ATTACHED];
  return uses.bases.map((one) => `${one.base} · read by ${one.agents.join(", ")}`);
}

/** Everything memory kept about a contact: the current facts, then the superseded ones, dimmed on a terminal. */
export function contact(remembered: ContactRemembered, dim = false): string[] {
  if (remembered.facts.length === 0) return [`nothing remembered about ${remembered.contact}`];
  return remembered.facts.map((fact) => factLine(fact, dim));
}

export function forgotten(gone: Forgotten): string {
  return `forgotten: ${gone.forgotten}`;
}

export const NOTHING_FORGOTTEN = "nothing forgotten";

/** The policy of the three corners. */
export function policy({ agent, answer }: Policy): string[] {
  const lines = [`${agent} · ${answer.world}`];
  for (const [name, row] of [["yours", answer.yours], ["team", answer.team], ["production", answer.production]] as const) {
    const memory = row?.config.memory ?? undefined;
    if (row === null) {
      lines.push(`  ${name.padEnd(12)}${name === "yours" ? "(team's)" : "nothing set"}`);
      continue;
    }
    if (memory === undefined) {
      lines.push(`  ${name.padEnd(12)}v${row.version} · nothing remembered`);
      continue;
    }
    lines.push(`  ${name.padEnd(12)}v${row.version}`);
    for (const line of memory.remember ?? []) lines.push(`    remember  ${line}`);
    for (const line of memory.forget ?? []) lines.push(`    forget    ${line}`);
  }
  return lines;
}

/** A recall score: a summary line, then one line per missed question. */
export function recall(one: MemoryScore): string[] {
  const figures = `memory · ${one.model} · ${one.questions} questions · recall@${one.k} ${one.recall_at_k.toFixed(2)} · nDCG@10 ${one.ndcg_at_10.toFixed(2)} · ${Math.round(one.took_ms)} ms`;
  return [figures, ...one.misses.map((missed) => `  missed: ${missed.asks} → wanted ${missed.missing.join(", ")}, got ${missed.found[0] ?? "nothing"}`)];
}

/** An extraction run: a summary line, then details for each failed case. */
export function extraction(answer: ExtractionRun): string[] {
  const counted = `${answer.cases} case${answer.cases === 1 ? "" : "s"}`;
  const lines = [`${answer.agent} · ${answer.model} · ${counted} · ${answer.held} held · ${Math.round(answer.took_ms)} ms`];
  for (const result of answer.results) {
    if (result.held) {
      lines.push(`  ${HELD} ${result.name}`);
      continue;
    }
    const broke = result.broke ?? [];
    const width = Math.max(0, ...broke.map((one) => one.check.length));
    lines.push(`  ${BROKEN} ${result.name}`);
    for (const one of broke) lines.push(`      ${one.check.padEnd(width)}  ${one.detail}`);
    for (const wrote of result.wrote ?? []) lines.push(`      kept      ${wrote}`);
    for (const refused of result.refused ?? []) lines.push(`      refused   ${refused}`);
  }
  return lines;
}

/** A fact with its category and, if superseded, the date it stopped holding (dimmed). */
export function factLine(fact: ContactFact, dim: boolean): string {
  const said = [`- ${fact.text}`];
  if (fact.category) said.push(`(${fact.category})`);
  if (fact.invalidated_at === null) return said.join(" ");
  said.push(`· until ${date(fact.invalidated_at)}`);
  const line = said.join(" ");
  return dim ? `${DIM}${line}${PLAIN}` : line;
}

function cornerOf(done: BaseAttached): string {
  return done.version === null ? done.corner : `${done.corner} v${done.version}`;
}
