/** Load the gateway-served widget and mount a tag that mints tokens with this key. */

import { post, type Credentials } from "@pinecall/core/api";
import { theBoxsOwnName } from "../../lib/mode";

// The gateway serves the widget with CORS, so sites embed this URL. Always the box's production
// name, never the sandbox's, since the snippet is pasted into real sites (lib/mode.ts).
export function widgetUrl(): string {
  return `${theBoxsOwnName()}/widget/pinecall-widget.js`;
}

let loading: Promise<void> | null = null;

/** Load the widget module from this gateway, once per page. */
export function loadWidget(): Promise<void> {
  loading ??= import(/* @vite-ignore */ widgetUrl()).then(
    () => undefined,
    (failed: unknown) => {
      loading = null;
      throw new Error(`the widget did not load from ${widgetUrl()}: ${failed instanceof Error ? failed.message : String(failed)}`);
    },
  );
  return loading;
}


/** Widget element properties: the token-minting functions. */
export interface WidgetElement extends HTMLElement {
  tokenProvider?: (scope: string, agent: string) => Promise<unknown>;
  codeProvider?: (agent: string) => Promise<unknown>;
  toggle?: () => void;
}

/**
 * Append a widget tag for this agent to `into`, minting tokens with this key. With `byPhone`,
 * "Call us" also uses the code door, as a site's code-url would.
 */
export function mountWidget(
  into: HTMLElement,
  credentials: Credentials,
  agent: string,
  attributes: Record<string, string>,
  byPhone = false,
): WidgetElement {
  const element = document.createElement("pinecall-widget") as WidgetElement;
  element.setAttribute("agent", agent);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  element.tokenProvider = (scope) => post(credentials, "/v1/tokens", { agent, scope, ttl_s: 60, metadata: { page: "console preview", scope } });
  if (byPhone) element.codeProvider = () => post(credentials, "/v1/codes", { agent });
  into.replaceChildren(element);
  return element;
}
