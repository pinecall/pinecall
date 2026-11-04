/** Colour for a terminal, on the marks and the hints alone: the data stays the terminal's own colour. */

const GREEN = "\u001b[32m";
const RED = "\u001b[31m";
const DIM = "\u001b[2m";
const PLAIN = "\u001b[0m";

/**
 * One line painted: a leading ✓ green, a leading ✗ red, a next step (`  → …`) or a mark that did not
 * apply (`  – …`) dimmed whole, the `pinecall:` of a refusal red. Anything else is left as it is.
 */
export function paintLine(line: string): string {
  if (line.startsWith("pinecall: ")) return `${RED}pinecall:${PLAIN}${line.slice("pinecall:".length)}`;
  // Two spaces: a tool call in a transcript opens with → too, at the line's start.
  if (/^ {2,}[→–] /.test(line)) return `${DIM}${line}${PLAIN}`;
  const mark = /^(\s*)([✓✗])( |$)/.exec(line);
  if (mark === null) return line;
  const [, lead = "", glyph = ""] = mark;
  return `${lead}${glyph === "✓" ? GREEN : RED}${glyph}${PLAIN}${line.slice(lead.length + glyph.length)}`;
}
