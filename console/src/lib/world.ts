/** Which world this page is: production at the root, the sandbox under `/sandbox`, read once when the page loads. */

export type World = "production" | "sandbox";

const SANDBOX = "sandbox";

export const WORLD: World = window.location.pathname.split("/").filter(Boolean)[0] === SANDBOX ? "sandbox" : "production";

/** The router's base in this world. */
export const WORLD_BASE: string = WORLD === "sandbox" ? `/${SANDBOX}` : "/";

/** A page's path as the browser's own, in that world. */
export function inWorld(world: World, page: string): string {
  return world === "sandbox" ? `/${SANDBOX}${page === "/" ? "" : page}` : page;
}

/** The browser's path with the world's prefix taken off. */
export function pageHere(): string {
  const path = window.location.pathname;
  if (WORLD !== "sandbox") return path;
  const page = path.slice(SANDBOX.length + 1);
  return page === "" ? "/" : page;
}
