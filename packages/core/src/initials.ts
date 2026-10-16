/** Avatar initials. */

/** First letter of the first two words, or the first two letters of a single word. */
export function initialsOf(words: string): string {
  const parts = words.split(/[\s@._-]+/).filter((part) => /[A-Za-z0-9]/.test(part));
  if (parts.length === 0) return "?";
  if (parts.length === 1) {
    const only = parts[0] ?? "";
    return (/^[A-Za-z]/.test(only) ? only.slice(0, 2) : only.slice(0, 1)).toUpperCase();
  }
  return `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}`.toUpperCase();
}
