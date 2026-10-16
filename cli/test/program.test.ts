/** The command tree pinned: every group's `--help` and every verb's under it, as the CLI prints them to no terminal, one file a group. */

import type { Command } from "@commander-js/extra-typings";
import { describe, expect, it } from "vitest";

import { createProgram } from "../src/program.js";
import { testContext } from "./support/context.js";
import { run } from "./support/run.js";

/** Every path under a command, the command's own first: `data`, `data erase`, `data erase call`, … */
export function pathsUnder(command: Command<unknown[], Record<string, unknown>, Record<string, unknown>>, above: string[] = []): string[][] {
  const here = [...above, command.name()];
  return [here, ...command.commands.flatMap((one) => pathsUnder(one as never, here))];
}

/** What one group's file holds: each path's help, headed by the path. */
export async function helpOfGroup(paths: string[][]): Promise<string> {
  const parts: string[] = [];
  for (const path of paths) {
    const ran = await run([...path, "--help"]);
    parts.push(`$ pinecall ${path.join(" ")} --help\n${ran.out}`);
  }
  return parts.join("\n");
}

const program = await createProgram(testContext().ctx);

describe("--help", () => {
  it("of the CLI itself", async () => {
    await expect((await run(["--help"])).out).toMatchFileSnapshot("./help/pinecall.txt");
  });

  for (const group of program.commands) {
    it(`of ${group.name()} and every verb under it`, async () => {
      await expect(await helpOfGroup(pathsUnder(group as never))).toMatchFileSnapshot(`./help/${group.name()}.txt`);
    });
  }
});
