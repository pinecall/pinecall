/** The command tree pinned: every group's `--help` and every verb's under it, as the CLI prints them to no terminal, one file a group. */

import type { Command } from "@commander-js/extra-typings";
import { describe, expect, it } from "vitest";

import { createProgram, versionIsAVerbs } from "../src/program.js";
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

describe("the version flag", () => {
  const versionOf = (program: Command): string | undefined => program.options.find((one) => one.long === "--version")?.flags;

  it("is the CLI's before any verb, with the root's own flags beside it", () => {
    for (const argv of [[], ["--help"], ["--version"], ["-v"], ["--prod", "--version"], ["--json", "-v", "--prod"], ["--version=2"]]) expect(versionIsAVerbs(argv), argv.join(" ")).toBe(false);
  });

  it("is the verb's after one: `test --version 2` is the settings' version, never this CLI's", () => {
    for (const argv of [["test", "--version", "2"], ["test", "--version=2"], ["--prod", "test", "--version", "99"], ["test", "--files", "-v"]]) expect(versionIsAVerbs(argv), argv.join(" ")).toBe(true);
  });

  it("the root has the flag unless the line gives it to a verb: commander would read it anywhere, and win", async () => {
    const { ctx } = testContext();
    expect(versionOf(await createProgram(ctx, ["--help"]))).toBe("-v, --version");
    expect(versionOf(await createProgram(ctx, ["test", "--version", "2"]))).toBeUndefined();
  });
});
