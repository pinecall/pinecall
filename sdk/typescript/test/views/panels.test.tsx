// Rendering views to console panel nodes.

import { describe, expect, it } from "vitest";

import { Badge, Panel, Row, Rows, Stat, Table, Text } from "../../src/views/panels.js";
import { renderToNodes } from "../../src/views/nodes.js";
import { renderToText } from "../../src/views/jsx-runtime.js";

describe("a view", () => {
  it("renders a panel as one node with its children under it", () => {
    const nodes = renderToNodes(
      <Panel title="Cliente">
        <Rows>
          <Row label="Alta">12 Mar 2024</Row>
          <Row label="Zona" value="Centro" />
        </Rows>
      </Panel>,
    );
    expect(nodes).toEqual([
      {
        tag: "panel",
        title: "Cliente",
        children: [
          {
            tag: "rows",
            children: [
              { tag: "row", label: "Alta", value: "12 Mar 2024" },
              { tag: "row", label: "Zona", value: "Centro" },
            ],
          },
        ],
      },
    ]);
  });

  it("writes a number out, wherever it is", () => {
    expect(renderToNodes(<Stat label="Servicios" value={3} />)).toEqual([{ tag: "stat", label: "Servicios", value: "3" }]);
  });

  it("reads a table's rows by the columns' own names", () => {
    const rows = [{ fecha: "12 Mar", servicio: "Mudanza", importe: 240 }];
    expect(renderToNodes(<Table columns={["fecha", "servicio", "importe"]} rows={rows} />)).toEqual([
      { tag: "table", columns: ["fecha", "servicio", "importe"], rows: [["12 Mar", "Mudanza", "240"]] },
    ]);
  });

  it("takes a row of a table in the columns' order too", () => {
    expect(renderToNodes(<Table columns={["a", "b"]} rows={[["uno", "dos"]]} />)).toEqual([
      { tag: "table", columns: ["a", "b"], rows: [["uno", "dos"]] },
    ]);
  });

  it("keeps a badge's tone, and falls back to neutral for a word it does not know", () => {
    expect(renderToNodes(<Badge tone="warn">con saldo</Badge>)).toEqual([{ tag: "badge", tone: "warn", text: "con saldo" }]);
    expect(renderToNodes(<Badge tone="turquoise">al día</Badge>)).toEqual([{ tag: "badge", tone: "neutral", text: "al día" }]);
  });

  it("draws nothing for what the view left out", () => {
    const missing = null;
    expect(renderToNodes(<Panel>{missing}<Text>{""}</Text></Panel>)).toEqual([{ tag: "panel", title: null, children: [] }]);
  });

  it("renders the tenant's own components, because a tag that is not the catalogue's is called", () => {
    const Since = ({ day }: { day: string }): ReturnType<typeof Row> => <Row label="Alta">{day}</Row>;
    expect(renderToNodes(<Since day="12 Mar 2024" />)).toEqual([{ tag: "row", label: "Alta", value: "12 Mar 2024" }]);
  });

  // Both renderers share JSX; a panel tag in a prompt would silently render as bare text.
  it("refuses a panel's tag inside a prompt, by name", () => {
    expect(() => renderToText(<Panel title="Cliente">Hola</Panel>)).toThrow(/<Panel> belongs to a view/);
  });
});
