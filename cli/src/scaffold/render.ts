/** Scaffold as a terminal reads it: the next steps of a new project, the files a generate wrote. */

import { NEXT, type Written } from "./service.js";

export function nextSteps(folder: string, written: Written): string[] {
  const next = NEXT[written.template];
  const first = written.agent === undefined ? ["  pinecall generate agent <name>   its first agent, under agents/<name>/"] : [];
  const what = written.agent === undefined ? `▸ ${folder} · a ${next.language} project, no agent yet` : `▸ ${folder} · a ${next.language} project · agents/${written.agent}/`;
  const runs = written.runs === undefined ? [] : [`  runs in ${written.runs.org} at ${written.runs.gateway} (pinecall.json)`];
  const signIn = written.runs === undefined ? ["  pinecall login       sign this machine in; the project runs in your org"] : [];
  return [
    what,
    ...runs,
    "",
    `  cd ${folder}`,
    `  ${next.install}`,
    ...first,
    ...signIn,
    "  pinecall chat        talk to it here",
    "  pinecall test        its goldens, against a real model",
    "  pinecall start       answer calls",
  ];
}

/** The orgs as a numbered list, for the terminal's question. */
export function orgChoices(slugs: string[]): string[] {
  return slugs.map((slug, at) => `  ${at + 1}. ${slug}`);
}

export function wrote(files: string[]): string[] {
  return files.map((file) => `  wrote ${file}`);
}
