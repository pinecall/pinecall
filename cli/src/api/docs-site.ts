/** docs.pinecall.io's llms-full.txt: every page of Pinecall's own docs in one file, read as the MCP server reads them. */

import { PinecallError } from "../errors.js";

export const DOCS_SITE = "https://docs.pinecall.io";

/** The site's one file of every page, as text. */
export async function getSiteText(site: string = DOCS_SITE): Promise<string> {
  const answered = await fetch(`${site}/llms-full.txt`);
  if (!answered.ok) throw new PinecallError(`${site}/llms-full.txt answered ${answered.status}`);
  return await answered.text();
}
