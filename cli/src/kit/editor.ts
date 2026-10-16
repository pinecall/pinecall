/** The person's own editor, opened on a text and waited for: the one place the CLI starts $EDITOR. */

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { UsageError } from "../errors.js";

/** Opens the text for editing and returns the result: $EDITOR, or a stub in tests. */
export type Editor = (text: string) => Promise<string>;

export const NO_EDITOR = "no editor: set $EDITOR (or $VISUAL, which wins over it) to the one that opens Markdown for you";
export const NO_TERMINAL = "an editor opens at a terminal: run this where stdin is one";

/** Edit in a temp file, like `git commit`; the directory is removed before returning. */
export async function editInEditor(text: string, env: NodeJS.ProcessEnv = process.env): Promise<string> {
  const editor = env["VISUAL"] ?? env["EDITOR"];
  if (editor === undefined || editor === "") throw new UsageError(NO_EDITOR);
  // Piped, the editor would wait on a stdin nobody types at.
  if (process.stdin.isTTY !== true) throw new UsageError(NO_TERMINAL);
  const folder = mkdtempSync(join(tmpdir(), "pinecall-edit-"));
  const file = join(folder, "text.md");
  try {
    writeFileSync(file, text);
    // Through a shell: $EDITOR may carry arguments (`code -w`). The path is quoted for spaces.
    const opened = spawnSync(`${editor} '${file.replaceAll("'", "'\\''")}'`, { stdio: "inherit", shell: true });
    if (opened.status !== 0) throw new UsageError(`${editor} exited with ${opened.status}: nothing written`);
    return readFileSync(file, "utf8");
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
}
