/** What `pinecall setup` shows: the wizard on a terminal, and the lines for one that is not. */

import type { Answers, Read } from "../service.js";

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
