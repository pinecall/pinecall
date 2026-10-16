/** Scaffold as a terminal reads it: the next steps of a new project, the files a generate wrote. */

import { NEXT, type Template } from "./service.js";

export function nextSteps(folder: string, template: Template, agent?: string): string[] {
  const next = NEXT[template];
  const first = agent === undefined ? ["  pinecall generate agent <name>   its first agent, under agents/<name>/"] : [];
  return [
    agent === undefined ? `▸ ${folder} · a ${next.language} project, no agent yet` : `▸ ${folder} · a ${next.language} project · agents/${agent}/`,
    "",
    `  cd ${folder}`,
    `  ${next.install}`,
    ...first,
    "  pinecall link        sign in, pick the org: its key goes to .env",
    "  pinecall chat        talk to it here",
    "  pinecall test        its goldens, against a real model",
    "  pinecall start       answer calls",
  ];
}

export function wrote(files: string[]): string[] {
  return files.map((file) => `  wrote ${file}`);
}
