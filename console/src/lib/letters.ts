/** A name's letters as one stable number (FNV-1a), for whatever a name is drawn with. */

export function lettersOf(name: string): number {
  let hash = 0x811c9dc5;
  for (const letter of name) hash = Math.imul(hash ^ (letter.codePointAt(0) ?? 0), 0x01000193);
  return hash >>> 0;
}
