/** Pinecall's own docs as the MCP server reads them: the site's one file cut into pages and sections, searched here. */

import { DOCS_SITE, getSiteText } from "../api/docs-site.js";

/** One page of the site. */
export interface SitePage {
  title: string;
  url: string;
  body: string;
}

/** One section of a page: what a search answers. */
export interface Found {
  title: string;
  section: string;
  url: string;
  score: number;
  snippet: string;
}

/** The site's pages, read from its llms-full.txt. */
export async function sitePages(site: string = DOCS_SITE): Promise<SitePage[]> {
  return pagesOf(await getSiteText(site));
}

// Every page whole, each under `# Title` and `Source: <url>`, in the sidebar's order.
const PAGE = /^# (.+)\nSource: (\S+)\n/gm;
const WORD = /[\p{L}\p{N}_@.-]{2,}/gu;
const SNIPPET = 400;

/** Cut the one file into its pages. */
export function pagesOf(text: string): SitePage[] {
  const heads = [...text.matchAll(PAGE)];
  return heads.map((head, at) => ({
    title: head[1]!,
    url: head[2]!,
    body: text.slice(head.index! + head[0].length, heads[at + 1]?.index ?? text.length).trim(),
  }));
}

/** The sections that answer the question best: the most of its words, then a title or heading that names them, then how often. */
export function searchPages(pages: readonly SitePage[], question: string, limit = 5): Found[] {
  const words = [...new Set((question.toLowerCase().match(WORD) ?? []).filter((word) => !STOP.has(word)))];
  if (words.length === 0) return [];
  const found: Found[] = [];
  for (const page of pages) {
    for (const { heading, text } of sectionsOf(page.body)) {
      const lower = text.toLowerCase();
      const head = `${page.title} ${heading}`.toLowerCase();
      // How many of the question's words a section holds counts most; how often, a little; a title or heading that holds them, more.
      let held = 0;
      let often = 0;
      let named = 0;
      for (const word of words) {
        const times = lower.split(word).length - 1;
        if (times > 0) (held += 1), (often += Math.log(1 + times));
        if (head.includes(word)) named += 1;
      }
      if (held === 0 && named === 0) continue;
      const score = 4 * held + often + 3 * named;
      found.push({
        title: page.title,
        section: heading,
        url: heading === "" ? page.url : `${page.url}#${anchorOf(heading)}`,
        score: Number(score.toFixed(2)),
        snippet: snippetOf(text, words),
      });
    }
  }
  return found.sort((a, b) => b.score - a.score).slice(0, limit);
}

/** A page by its address or its path on the site. */
export function pageAt(pages: readonly SitePage[], where: string): SitePage | undefined {
  const path = (where.replace(DOCS_SITE, "").split("#")[0] ?? "").replace(/^\/+|\/+$/g, "");
  return pages.find((page) => page.url.replace(DOCS_SITE, "").replace(/^\/|\/$/g, "") === path);
}

function sectionsOf(body: string): { heading: string; text: string }[] {
  const parts = body.split(/^## (.+)$/m);
  const sections = [{ heading: "", text: parts[0] ?? "" }];
  for (let at = 1; at < parts.length; at += 2) sections.push({ heading: parts[at]!.trim(), text: parts[at + 1] ?? "" });
  return sections;
}

// As the site makes a heading's id: lower case, letters, digits, spaces and dashes, each space a dash.
function anchorOf(heading: string): string {
  return heading.toLowerCase().replace(/[^\p{L}\p{N}\p{M} _-]/gu, "").replaceAll(" ", "-");
}

function snippetOf(text: string, asked: string[]): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const at = Math.max(0, Math.min(...asked.map((word) => flat.toLowerCase().indexOf(word)).filter((index) => index >= 0)) - 80);
  return `${at > 0 ? "…" : ""}${flat.slice(at, at + SNIPPET)}${flat.length > at + SNIPPET ? "…" : ""}`;
}

const STOP = new Set(["the", "a", "an", "of", "to", "in", "on", "is", "it", "and", "or", "for", "how", "do", "does", "i", "my", "what", "with", "can", "be", "are", "el", "la", "de", "que", "en", "y", "un", "una", "como", "es"]);
