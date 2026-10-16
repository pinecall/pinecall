/** Calls started by this tab, which never raise a corner window. */

// Module-level: Talk writes it and the shell's corner windows read it.
const started = new Set<string>();

export function ours(call: string): void {
  started.add(call);
}

export function isOurs(call: string): boolean {
  return started.has(call);
}
