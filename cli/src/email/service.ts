/** The org's email layout: shown, set from a file, cleared, and tried on words before a contact reads it. */

import { existsSync, readFileSync, writeFileSync } from "node:fs";

import { z } from "zod";

import * as api from "../api/email.js";
import type { Context } from "../context.js";
import { UsageError } from "../errors.js";

/** Where a reply goes in a layout, once. */
export const CONTENT = "{{content}}";

/** What `email layout preview` takes: the words, the subject they answer, a layout to try, where to write the HTML. */
export const PreviewInput = z.object({
  text: z.string().min(1, "the words a reply would say"),
  subject: z.string().optional(),
  file: z.string().optional(),
  out: z.string().optional(),
});
export type PreviewInput = z.infer<typeof PreviewInput>;

/** A preview, and the file its HTML was written to when one was named. */
export interface Previewed extends api.EmailPreview {
  written: string | null;
}

export async function showLayout(ctx: Context): Promise<api.EmailLayout> {
  return api.getEmailLayout(ctx.gateway());
}

/** The file's HTML kept as the org's layout; refused here when it says nowhere where the reply goes. */
export async function setLayout(ctx: Context, file: string): Promise<api.EmailLayout> {
  return api.putEmailLayout(ctx.gateway(), htmlOf(file));
}

export async function clearLayout(ctx: Context): Promise<{ cleared: true }> {
  await api.deleteEmailLayout(ctx.gateway());
  return { cleared: true };
}

/** The words set in the org's layout (or the file's), as the contact would read them; nothing is sent. */
export async function previewLayout(ctx: Context, input: PreviewInput): Promise<Previewed> {
  const body: { text: string; subject?: string; html?: string } = { text: input.text };
  if (input.subject !== undefined) body.subject = input.subject;
  if (input.file !== undefined) body.html = htmlOf(input.file);
  const preview = await api.previewEmail(ctx.gateway(), body);
  if (input.out !== undefined) writeFileSync(input.out, preview.html);
  return { ...preview, written: input.out ?? null };
}

function htmlOf(file: string): string {
  if (!existsSync(file)) throw new UsageError(`no file ${file}: an HTML file that says ${CONTENT} where the reply goes`);
  const html = readFileSync(file, "utf8");
  if (html.split(CONTENT).length !== 2) throw new UsageError(`${file} says ${CONTENT} ${html.includes(CONTENT) ? "more than once" : "nowhere"}: once, where the reply goes`);
  return html;
}
