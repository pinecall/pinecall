/** Render the agent class's view as the console panel for one conversation. */

import { DevRefused } from "../client/index.js";

import { viewOf, type Who } from "../agent/view.js";
import { renderToNodes, type ViewNode } from "../views/nodes.js";

// The console falls back to its own contact panel on this 404.
const DRAWS_NONE = (agent: string): string => `${agent} declares no view: nothing in this directory draws a panel`;

/** Rendered panel: its title and node tree. */
export interface Drawn {
  name: string;
  nodes: ViewNode[];
}

/** This process's answer to `view.render`, for the class it serves. */
export interface Viewing {
  render(asked: unknown): Promise<Drawn>;
}

/**
 * Bind `view.render` to a class. The view may be async; its output is rendered to
 * `@pinecall/agents/panels` nodes, so only data reaches the browser.
 */
export function viewingFrom(ctor: object, slug: string): Viewing {
  return {
    async render(asked: unknown): Promise<Drawn> {
      const said = aConversation(asked);
      const who: Who = { agent: slug, contact: said.contact, call: said.call };
      const declared = viewOf(ctor);
      if (declared === undefined) throw new DevRefused(404, DRAWS_NONE(slug));
      // Report a throwing view in the pane instead of breaking the conversation screen.
      try {
        return { name: declared.name, nodes: renderToNodes(await declared.draw(who)) };
      } catch (failed) {
        throw new DevRefused(502, `${slug}'s view failed: ${failed instanceof Error ? failed.message : String(failed)}`);
      }
    },
  };
}

function aConversation(asked: unknown): { contact: string; call: string } {
  if (typeof asked !== "object" || asked === null || Array.isArray(asked)) {
    throw new DevRefused(422, "a panel is asked for with a JSON object");
  }
  const said = asked as Record<string, unknown>;
  return { contact: aName(said, "contact"), call: aName(said, "call") };
}

function aName(said: Record<string, unknown>, name: string): string {
  const value = said[name];
  if (typeof value !== "string" || value === "") throw new DevRefused(422, `${name} is a name, and it was missing`);
  return value;
}
