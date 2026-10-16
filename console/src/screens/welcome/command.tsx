/** One line to type, as a small terminal: the `$` line and a copy button. */

import type { ReactNode } from "react";

import { Terminal } from "./terminal";

export function Command({ line, say }: { line: string; say?: string }): ReactNode {
  return <Terminal lines={[{ say: say ?? "in a terminal", run: line }]} />;
}
