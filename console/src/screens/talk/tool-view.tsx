/** A finished tool run drawn as what its answer means, under its card's head: chips, rows, a receipt or code (tool-shape.ts reads which). */

import type { ReactNode } from "react";

import { type Shape } from "./tool-shape";
import "./tool-view.css";

export function ToolView({ shape }: { shape: Shape }): ReactNode {
  switch (shape.kind) {
    case "chips":
      return (
        <div className="talk-view-chips">
          {shape.items.map((item, at) => (
            <span key={at} className="talk-view-chip" style={{ animationDelay: `${at * 30}ms` }}>
              {item}
            </span>
          ))}
          {shape.more > 0 && <span className="talk-view-more">+{shape.more} more</span>}
        </div>
      );
    case "rows":
      return (
        <ul className="talk-view-rows">
          {shape.items.map((item, at) => (
            <li key={at} className="talk-view-row" style={{ animationDelay: `${at * 30}ms` }}>
              <span className="talk-view-head">{item.head}</span>
              {item.rest !== "" && <span className="talk-view-rest">{item.rest}</span>}
            </li>
          ))}
          {shape.more > 0 && <li className="talk-view-more">+{shape.more} more</li>}
        </ul>
      );
    case "receipt":
      return (
        <dl className="talk-view-receipt">
          {shape.fields.map((field) => (
            <div key={field.name} className="talk-view-field">
              <dt>{field.name}</dt>
              <dd>{field.value}</dd>
            </div>
          ))}
        </dl>
      );
    case "code":
      return <pre className="talk-view-code">{shape.text}</pre>;
  }
}
