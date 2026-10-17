/** What `pinecall setup` shows: the wizard on a terminal, and the lines for one that is not. */

import type { Answers, Read, RemoteAdvice } from "../service.js";

export { wizard, type WizardInput } from "./wizard.js";

/** The machine and the stack recommended, as lines: what `setup --recommend` prints to a person. */
export function recommendationLines(read: Read): string[] {
  const { machine, recommendation } = read;
  const runsOn =
    recommendation.on === "gpu"
      ? machine.cards.map((card) => `${card.name} · ${card.memory_gib} GB`).join(" + ")
      : recommendation.on === "apple"
        ? `Apple silicon · ${machine.ram_gib} GB unified`
        : `no GPU · ${machine.cores} cores · ${machine.ram_gib} GB`;
  const lines = [
    `this machine  ${runsOn}${recommendation.on === "cpu" ? "" : ` · ${recommendation.budget_gib} GB for the models`}`,
    `here          docker ${machine.docker ? "✓" : "✗"} · ollama ${machine.ollama_here ? "✓" : "the container"} · ${machine.system} ${machine.arch}`,
    `keys set      ${machine.keys_found.length === 0 ? "none" : machine.keys_found.join(", ")}`,
    "",
    `${"measured".padEnd(40)}${"fits".padEnd(11)}first token  message  docs  talk`,
    ...recommendation.candidates.map(
      (one) =>
        `${one.model.padEnd(40)}${(one.fits ? "✓" : `✗ -${one.short_by_gib} GB`).padEnd(11)}${`${one.first_token_s}s`.padEnd(13)}${one.message.padEnd(9)}${one.documents.padEnd(6)}${one.talk}`,
    ),
    "",
    `recommended   stt ${recommendation.stack["stt"]} · turn ${recommendation.stack["turn"]} · llm ${recommendation.stack["llm"]} · tts ${recommendation.stack["tts"]}`,
    ...recommendation.notes.map((note) => `! ${note}`),
  ];
  return lines;
}

/** A host's advice, as lines: each stage's choice and whose key it runs on, then how an agent takes it. */
export function adviceLines(advice: RemoteAdvice): string[] {
  const lends = advice.lends === null ? "every vendor it holds a key for" : advice.lends.length === 0 ? "nothing" : advice.lends.join(", ");
  const lines = [`this runtime  ${advice.url} · lends ${lends}`, ""];
  const width = Math.max(...advice.stages.map((one) => one.choice.length)) + 2;
  for (const one of advice.stages) {
    lines.push(`${(STAGE_NAMES[one.stage] ?? one.stage).padEnd(13)}${one.choice.padEnd(width)}${one.runsOn}`);
    if (one.served.length > 0) lines.push(`${"".padEnd(13)}served there: ${one.served.join(", ")}`);
    if (one.key !== undefined) lines.push(`${"".padEnd(13)}${one.key.variable}: ${one.key.where}`);
  }
  if (advice.judge !== null || advice.caller !== null) lines.push("", `judge        ${advice.judge ?? "-"} · caller ${advice.caller ?? "-"} (the host's, on its keys)`);
  const choice = (stage: string): string => advice.stages.find((one) => one.stage === stage)?.choice ?? "";
  lines.push("", `for an agent pinecall agent set --agent <name> --stt ${choice("stt")} --llm ${choice("llm")} --tts ${choice("tts")}`);
  if (advice.machine !== null) lines.push("", "its machine, as its operator sees it: pinecall setup --recommend --json");
  return lines;
}

const STAGE_NAMES: Record<string, string> = { stt: "ears", llm: "thinking", tts: "voice" };

/** The answers about to run, one line each. */
export function answersLines(answers: Answers): string[] {
  return [
    `ears        ${answers.stt}`,
    `end of turn ${answers.turn}`,
    `thinking    ${answers.llm}`,
    `voice       ${answers.tts}`,
    `judge       ${answers.judge}`,
    `caller      ${answers.caller}`,
    ...(answers.chatOnly ? ["written calls alone: no LiveKit, no worker"] : []),
  ];
}
