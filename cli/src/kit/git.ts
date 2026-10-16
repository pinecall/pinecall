/** What git says about a file: the one place the CLI asks it. */

import { spawnSync } from "node:child_process";
import { dirname } from "node:path";

/**
 * Whether git ignores this file, per `git check-ignore`. Also true outside a repository or
 * without git, since nothing can commit it there.
 */
export function ignoredByGit(file: string): boolean {
  const checked = spawnSync("git", ["check-ignore", "-q", file], { cwd: dirname(file), stdio: "ignore" });
  // 0 ignored · 1 not ignored · 128 not a repository; an error is no git on this machine.
  return checked.error !== undefined || checked.status !== 1;
}
