/** The version this CLI was published as: its own package.json's. */

import { readFileSync } from "node:fs";

/** The CLI's version, as npm installed it. */
export function version(): string {
  const ours = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as { version: string };
  return ours.version;
}
