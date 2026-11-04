/** Commander's usage errors said in the CLI's own voice: the verbs typed, what they take, and where their help is. */

import type { Command, CommanderError, CommandUnknownOpts } from "@commander-js/extra-typings";

import { UsageError } from "../errors.js";

/** The verbs typed, as far as the tree knows them: `lexicon add` from `pinecall --prod lexicon add DKV --say x`. */
export function verbsTyped(program: Command, argv: readonly string[]): string[] {
  const verbs: string[] = [];
  let at: CommandUnknownOpts = program;
  for (const word of argv) {
    if (word.startsWith("-")) continue;
    const next = at.commands.find((one) => one.name() === word || one.aliases().includes(word));
    if (next === undefined) break;
    verbs.push(word);
    at = next;
  }
  return verbs;
}

/** Commander's error as the CLI's sentence: what was typed, what the verb takes, and the `--help` that says so. */
export function usageErrorOf(failed: CommanderError, verbs: readonly string[]): UsageError {
  const said = failed.message.replace(/^error: /, "").replace(/\n\(Did you mean (.+)\?\)$/, " (did you mean $1?)");
  const typed = ["pinecall", ...verbs].join(" ");
  const help = `\`${typed} --help\``;
  switch (failed.code) {
    case "commander.unknownCommand": {
      const name = /^unknown command '([^']+)'(.*)$/.exec(said);
      return new UsageError(`no verb ${name?.[1] ?? said}${name?.[2] ?? ""}: ${help} lists them`);
    }
    case "commander.unknownOption": {
      const flag = /^unknown option '([^']+)'(.*)$/.exec(said);
      return new UsageError(`${typed} has no option ${flag?.[1] ?? said}${flag?.[2] ?? ""}: ${help} shows its flags`);
    }
    case "commander.excessArguments": {
      const counted = /Expected (\d+) arguments? but got (\d+)/.exec(said);
      const expected = Number(counted?.[1] ?? 0);
      const takes = expected === 0 ? "takes nothing after it" : `takes ${expected} argument${expected === 1 ? "" : "s"}`;
      return new UsageError(`${typed} ${takes}, and ${counted?.[2] ?? "more"} were typed: ${help} says what it takes`);
    }
    case "commander.missingArgument": {
      const name = /^missing required argument '([^']+)'/.exec(said);
      return new UsageError(`${typed} needs a <${name?.[1] ?? "argument"}>: ${help} says what it takes`);
    }
    case "commander.missingMandatoryOptionValue": {
      const flags = /^required option '([^']+)'/.exec(said);
      return new UsageError(`${typed} needs ${flags?.[1] ?? "a flag"}: ${help} shows its flags`);
    }
    case "commander.optionMissingArgument": {
      const flags = /^option '([^']+)' argument missing/.exec(said);
      return new UsageError(`${typed}: ${flags?.[1] ?? "the flag"} takes a value, and none was typed: ${help} shows its flags`);
    }
    default:
      return new UsageError(`${said}: ${help}`);
  }
}
