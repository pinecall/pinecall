/** The docs tools: `docs_search` finds the sections of docs.pinecall.io that answer a question, `get_doc` reads a page whole. */

import { z } from "zod";

import { pageAt, searchPages, sitePages, type SitePage } from "../site.js";
import type { Session } from "../session.js";
import { tool, ToolRefused } from "../tool.js";

const LONGEST_PAGE = 30_000;

export const docsSearch = tool({
  name: "docs_search",
  description: "Search Pinecall's own docs (docs.pinecall.io) and answer the sections that best match, each with its address and a snippet.",
  schema: {
    question: z.string().min(2).describe("what you want to know, in a few words"),
    limit: z.number().int().min(1).max(10).optional().describe("how many sections, the best first; 5 when left out"),
  },
  manual:
    "`docs_search` finds the sections of docs.pinecall.io that answer a question — a verb, a decorator, a setting, a judge — each with its address. Read the page whole with `get_doc` before writing code from it: a snippet has no imports and no caveats.",
  handler: async (args, ctx) => ({ found: searchPages(await pagesOf(ctx.session), args.question, args.limit ?? 5) }),
});

export const getDoc = tool({
  name: "get_doc",
  description: "Read one page of docs.pinecall.io whole, by its address or its path (such as concepts/tools).",
  schema: {
    page: z.string().describe("the page's address, or its path on the site"),
    offset: z.number().int().min(0).optional().describe("where to start reading a long page, in characters"),
  },
  manual: "`get_doc` reads a page of the docs whole, as Markdown, by the address `docs_search` answered or by its path.",
  handler: async (args, ctx) => {
    const page = pageAt(await pagesOf(ctx.session), args.page);
    if (page === undefined) throw new ToolRefused(`no page at ${args.page}: \`docs_search\` finds one`);
    const offset = args.offset ?? 0;
    const body = page.body.slice(offset, offset + LONGEST_PAGE);
    const more = page.body.length > offset + LONGEST_PAGE;
    return { title: page.title, url: page.url, body, ...(more ? { next_offset: offset + LONGEST_PAGE } : {}) };
  },
});

// Read once per server: the site changes when it is deployed, not while an assistant works.
async function pagesOf(session: Session): Promise<SitePage[]> {
  session.site ??= sitePages();
  try {
    return await session.site;
  } catch (failed) {
    session.site = undefined;
    throw failed;
  }
}
