/** A secret's name as the gateway takes one: an environment variable's, and never one the box sets itself. */

const A_NAME = /^[A-Z][A-Z0-9_]*$/;

/** Why a name would be refused, in the page's words; null when the gateway would take it. */
export function nameRefused(name: string): string | null {
  if (name === "") return "Name it: the variable the app reads, like CRM_TOKEN.";
  if (!A_NAME.test(name)) return "A name is an environment variable's: capitals, digits and underscores, starting with a capital.";
  if (name.startsWith("PINECALL_")) return "A name starting with PINECALL_ is the box's own: it sets those itself.";
  return null;
}
