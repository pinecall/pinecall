/** Renders an agent's view tree with console components; views carry data, never markup. */

import type { ReactNode } from "react";

import { KV, Pill, SectionLabel, TableHead, TableRow } from "../../ui";
import type { ViewNode } from "./view-door";

// Tenants pick a semantic tone; the console maps it to colours, so tenant data never reaches styling.
const TONES = { neutral: "gray", good: "green", warn: "amber", bad: "red" } as const;

export function Drawing({ nodes }: { nodes: ViewNode[] }): ReactNode {
  return (
    <>
      {nodes.map((node, index) => (
        <Node key={index} node={node} />
      ))}
    </>
  );
}

function Node({ node }: { node: ViewNode }): ReactNode {
  switch (node.tag) {
    case "panel":
      return (
        <div className="ib-panel">
          {node.title !== null && <SectionLabel>{node.title}</SectionLabel>}
          <Drawing nodes={node.children} />
        </div>
      );
    case "rows":
      return (
        <div className="ib-panel-rows">
          <Drawing nodes={node.children} />
        </div>
      );
    case "row":
      return <KV label={node.label}>{node.value}</KV>;
    case "stat":
      return (
        <div className="ib-panel-stat">
          <span className="ib-panel-stat-value">{node.value}</span>
          <span className="ib-panel-stat-label">{node.label}</span>
        </div>
      );
    case "table":
      return <Grid columns={node.columns} rows={node.rows} />;
    case "badge":
      return (
        <div className="ib-panel-badge">
          <Pill tone={TONES[node.tone]} small>
            {node.text}
          </Pill>
        </div>
      );
    case "text":
      return <p className="ib-panel-text">{node.text}</p>;
  }
}

function Grid({ columns, rows }: { columns: string[]; rows: string[][] }): ReactNode {
  if (rows.length === 0) return <p className="ib-panel-text">—</p>;
  const wide = `repeat(${String(Math.max(columns.length, rows[0]?.length ?? 1))}, minmax(0, 1fr))`;
  return (
    <div className="ib-panel-table">
      {columns.length > 0 && <TableHead columns={wide} labels={columns} padding="5px 2px" />}
      {rows.map((cells, index) => (
        <TableRow key={index} columns={wide} padding="6px 2px">
          {cells.map((cell, cellIndex) => (
            <span key={cellIndex} className="ui-clip">
              {cell}
            </span>
          ))}
        </TableRow>
      ))}
    </div>
  );
}
