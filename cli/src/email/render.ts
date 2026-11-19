/** What the email verbs print: how the org's emails are set, a preview, a layout cleared. */

import type { EmailLayout } from "../api/email.js";
import { formatHint } from "../kit/format.js";
import type { Previewed } from "./service.js";

export function layout(kept: EmailLayout): string[] {
  if (kept.text_only === true) return ["text alone: no template, and no HTML part in the org's emails", formatHint("pinecall email layout set <file.html> sets them in a layout · pinecall email layout clear goes back to the plain one")];
  const whose = kept.own ? "the org's own layout" : "the plain layout: the org wrote none";
  const next = kept.own ? 'pinecall email layout preview "<words>" shows a reply in it' : "pinecall email layout set <file.html> keeps one of yours";
  return [`${whose} · ${kept.html.length.toLocaleString("en-US")} characters`, formatHint(next)];
}

export function preview(shown: Previewed): string[] {
  const lines = [`subject  ${shown.subject}`, "", ...shown.text.split("\n").map((line) => `  ${line}`), ""];
  if (shown.html === null) lines.push("text alone: this is the whole email, with no HTML part");
  else lines.push(shown.written === null ? `${shown.html.length.toLocaleString("en-US")} characters of HTML · --out <file.html> writes them` : `HTML written to ${shown.written}`);
  return lines;
}

export function cleared(): string {
  return "the org's layout forgotten: its agents' emails are set in the plain one";
}
