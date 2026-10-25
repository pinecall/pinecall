// The gateway's answer to one request: the sentence of its refusal.

/** The `detail` of an error body, or the raw body. */
export function detailOf(text: string): string {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    return typeof parsed.detail === "string" ? parsed.detail : text;
  } catch {
    return text;
  }
}
