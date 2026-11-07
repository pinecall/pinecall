/** Nothing yet: one card in place of a screen's empty ones — a faded sketch of what is coming, what fills it, and the way there. */

import type { ReactNode } from "react";

import { Card } from "./card";

/** `art` is the screen's own sketch, drawn faded; `actions` its buttons, the first the way forward. */
export function Nothing({ art, title, children, actions }: { art: ReactNode; title: string; children: ReactNode; actions: ReactNode }): ReactNode {
  return (
    <Card pad>
      <div className="ui-nothing">
        <div className="ui-nothing-art" aria-hidden>
          {art}
        </div>
        <h2 className="ui-nothing-title">{title}</h2>
        <p className="ui-nothing-words">{children}</p>
        <div className="ui-nothing-actions">{actions}</div>
      </div>
    </Card>
  );
}
