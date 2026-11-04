/** Commander's usage errors said in the CLI's own voice, and every failure as the two lines a person reads. */

import type { Command, CommanderError, CommandUnknownOpts } from "@commander-js/extra-typings";

import { UsageError } from "../errors.js";
import { formatNotice } from "./format.js";

/** The verbs typed as far as the tree knows them, and the command they reach: `lexicon add` from `pinecall --prod lexicon add DKV --say x`. */
export function readCommandTyped(program: Command, argv: readonly string[]): { verbs: string[]; leaf: CommandUnknownOpts } {
  const verbs: string[] = [];
  let leaf: CommandUnknownOpts = program;
  for (const word of argv) {
    if (word.startsWith("-")) continue;
    const next = leaf.commands.find((one) => one.name() === word || one.aliases().includes(word));
    if (next === undefined) break;
    verbs.push(word);
    leaf = next;
  }
  return { verbs, leaf };
}

/** Commander's error as the CLI's sentence: what was typed, what the verb takes, and the `--help` that says so. */
export function usageErrorOf(failed: CommanderError, verbs: readonly string[], leaf?: CommandUnknownOpts): UsageError {
  const said = failed.message.replace(/^error: /, "").replace(/\n\(Did you mean (.+)\?\)$/, " (did you mean $1?)");
  // The verbs alone name what was typed: `lexicon add`, or `pinecall` when no verb was.
  const typed = verbs.length === 0 ? "pinecall" : verbs.join(" ");
  const help = `\`${["pinecall", ...verbs].join(" ")} --help\``;
  switch (failed.code) {
    case "commander.unknownCommand": {
      const name = /^unknown command '([^']+)'(.*)$/.exec(said);
      return new UsageError(`no verb ${name === null ? said : `"${name[1]}"${name[2]}`}: \`pinecall --help\` lists them`);
    }
    case "commander.unknownOption": {
      const flag = /^unknown option '([^']+)'(.*)$/.exec(said);
      return new UsageError(`${typed} has no option ${flag?.[1] ?? said}${flag?.[2] ?? ""}: ${help} shows its flags`);
    }
    case "commander.excessArguments": {
      const expected = Number(/Expected (\d+) arguments?/.exec(said)?.[1] ?? 0);
      const words = leaf?.args ?? [];
      const takes = expected === 0 ? "takes no argument" : `takes ${expected} argument${expected === 1 ? "" : "s"}`;
      const was = words.length === 0 ? "more were typed" : `"${words.join(" ")}" was typed`;
      // `agent clear language`: the word is one of the verb's flags, typed without its dashes.
      const flag = leaf?.options.find((one) => words.some((word) => one.long === `--${word}`));
      const fix = flag?.long === undefined ? `${help} says what it takes` : `\`pinecall ${verbs.join(" ")} ${flag.long}\``;
      return new UsageError(`${typed} ${takes}, and ${was}: ${fix}`);
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
      return new UsageError(`${flags?.[1] ?? "the flag"} takes a value, and none was typed: ${help} shows its flags`);
    }
    default:
      return new UsageError(`${said}: ${help}`);
  }
}

/** A failure as a person reads it: `pinecall: <what happened>`, then the next step on its own line. */
export function formatFailure(message: string): string[] {
  const [said = message, ...step] = formatNotice(message);
  return [`pinecall: ${said}`, ...step];
}
