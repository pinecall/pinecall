/** `<Screen>`: an agent's screen drawn with the page's own components, one per part. */

import { createElement, Fragment, type ComponentType, type ReactNode } from "react";

import type { Screen as Drawn, ScreenNode } from "../index.js";

/** The page's component for each part the agent names. A part with none is not drawn. */
// A part's props are the agent's to choose, so no one type fits every component of the map.
export type Parts = Record<string, ComponentType<any>>;

export interface ScreenProps {
  /** `screenOf(state.log)`. */
  screen: Drawn;
  parts: Parts;
  /** Told the name of a part the page has no component for. */
  onUnknown?: ((part: string) => void) | undefined;
}

/** Draw a screen: each part with the component of its name, given the part's props and what it holds as children. */
export function Screen({ screen, parts, onUnknown }: ScreenProps): ReactNode {
  const draw = (one: ScreenNode | string, at: number): ReactNode => {
    if (typeof one === "string") return createElement(Fragment, { key: at }, one);
    const drawnBy = parts[one.part];
    if (drawnBy === undefined) {
      onUnknown?.(one.part);
      return null;
    }
    return createElement(drawnBy, { ...one.props, key: `${one.part}-${at}` }, ...one.children.map(draw));
  };
  return createElement(Fragment, null, ...screen.map(draw));
}
