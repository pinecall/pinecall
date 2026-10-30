// The hold melody a class declares: the file beside it named by its hash in the declaration, and uploaded once the agent registers.

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";

import type { Agent } from "../agent/agent.js";
import type { HoldDeclaration } from "../agent/melody.js";
import { DeclarationRefused } from "../agent/tools.js";
import type { Pinecall } from "../client/index.js";
import type { AgentConfig } from "../wire/agent-config.js";
import type { Camel } from "../wire/codec.js";

const NOT_A_HOLD = "hold is the melody: { file: \"hold.mp3\", afterS: 1.5 }, { afterS }, { off: true } or \"off\"";
const NO_SUCH_FILE = (path: string): string => `hold names ${path}, and there is no such file beside the class`;

/** What the class declares of its melody, as the wire carries it: the file by hash, the wait, silence; undefined for none. */
export function holdConfigOf(ctor: typeof Agent, file: string | undefined): Camel<AgentConfig>["hold"] | undefined {
  const declared = ctor.hold;
  if (declared === undefined) return undefined;
  if (declared === "off") return { off: true };
  if (typeof declared !== "object" || declared === null) throw new DeclarationRefused(NOT_A_HOLD);
  const hold: NonNullable<Camel<AgentConfig>["hold"]> = {};
  if (declared.afterS !== undefined) hold.afterS = declared.afterS;
  if (declared.off === true) hold.off = true;
  if (declared.file !== undefined) {
    const read = melodyOf(declared, file);
    hold.clip = read.sha256;
    hold.name = read.name;
  }
  return hold;
}

/** The file the class ships as its melody, read beside the class: its bytes, its name, its sha256. */
export function melodyOf(declared: HoldDeclaration, file: string | undefined): { bytes: Uint8Array; name: string; sha256: string } {
  if (declared.file === undefined) throw new DeclarationRefused(NOT_A_HOLD);
  const path = file === undefined ? resolve(declared.file) : resolve(dirname(resolve(file)), declared.file);
  if (!existsSync(path)) throw new DeclarationRefused(NO_SUCH_FILE(path));
  const bytes = readFileSync(path);
  return { bytes, name: basename(path), sha256: createHash("sha256").update(bytes).digest("hex") };
}

/**
 * The class's melody uploaded once the agent registers, when the gateway does not hold that file
 * yet: the door keeps the hash of what was uploaded, so a second start with the same file sends nothing.
 */
export async function uploadDeclaredHold(pc: Pinecall, ctor: typeof Agent, file: string | undefined, slug: string, report: ((line: string) => void) | undefined): Promise<void> {
  const declared = ctor.hold;
  if (declared === undefined || declared === "off" || declared.file === undefined) return;
  const melody = melodyOf(declared, file);
  const held = await pc.holdAudio(slug);
  if (held.sourceSha256 === melody.sha256) return;
  const landed = await pc.uploadHoldAudio(slug, melody.bytes, melody.name);
  report?.(`${slug}  ${melody.name} uploaded as the hold melody · ${landed.seconds ?? "?"} s`);
}
