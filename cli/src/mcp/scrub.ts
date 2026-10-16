/** No secret crosses a model: every answer and every refusal of the MCP server passes here first. */

// A Pinecall key, a server's token or a console's one-use login code, wherever it appears.
const SHAPED = /\b(?:pc_(?:live|test)_|pk_|lc_)[A-Za-z0-9_-]{6,}/g;

export const HIDDEN = "***";

/** The text with every secret it knows of, and every one shaped like a Pinecall key, hidden — but for the values a tool reveals. */
export function scrub(text: string, secrets: readonly string[] = [], revealed: readonly string[] = []): string {
  const kept = revealed.filter((one) => one.length > 0);
  let clean = kept.reduce((said, one, at) => said.replaceAll(one, `\u0000${at}\u0000`), text);
  for (const secret of secrets) if (secret.length >= 6) clean = clean.replaceAll(secret, HIDDEN);
  clean = clean.replace(SHAPED, HIDDEN);
  return clean.replace(/\u0000(\d+)\u0000/g, (_whole, at: string) => kept[Number(at)] ?? "");
}
