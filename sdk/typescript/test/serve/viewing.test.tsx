// The panel this process draws for one conversation: the class's own view, rendered to a tree.

import { describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { view, type Who } from "../../src/agent/view.js";
import { DevRefused } from "../../src/client/index.js";
import { viewingFrom } from "../../src/serve/viewing.js";
import { Panel, Row } from "../../src/views/panels.js";

const WHO = { contact: "+34600000001", call: "CA_1" };

// A view reads the tenant's own systems, which is why it may be async: this one stands for the
// CRM call every real one makes.
async function CustomerCard(who: Who): Promise<ReturnType<typeof Panel>> {
  await Promise.resolve();
  return (
    <Panel title="Cliente">
      <Row label="Teléfono">{who.contact}</Row>
      <Row label="Agente">{who.agent}</Row>
    </Panel>
  );
}

@view(CustomerCard, "Cliente")
class ClinicaNorte extends Agent {
  web = true;
}

class Sencilla extends Agent {
  web = true;
}

describe("view.render", () => {
  it("renders the class's view for the conversation asked about", async () => {
    expect(await viewingFrom(ClinicaNorte, "clinica-norte").render(WHO)).toEqual({
      name: "Cliente",
      nodes: [
        {
          tag: "panel",
          title: "Cliente",
          children: [
            { tag: "row", label: "Teléfono", value: "+34600000001" },
            { tag: "row", label: "Agente", value: "clinica-norte" },
          ],
        },
      ],
    });
  });

  it("refuses a class that draws no panel, in a sentence that says where one would live", async () => {
    await expect(viewingFrom(Sencilla, "sencilla").render(WHO)).rejects.toThrow(/declares no view/);
  });

  it("asks for the conversation it is about, and says so when it is missing", async () => {
    await expect(viewingFrom(ClinicaNorte, "clinica-norte").render({ call: "CA_1" })).rejects.toMatchObject({ status: 422 });
  });

  it("hands a view that threw back as the tenant's own failure, not as a broken screen", async () => {
    function Broken(): never {
      throw new Error("the CRM is down");
    }
    @view(Broken)
    class Rota extends Agent {
      web = true;
    }
    const failed = await viewingFrom(Rota, "rota")
      .render(WHO)
      .catch((refused: unknown) => refused);
    expect(failed).toBeInstanceOf(DevRefused);
    expect((failed as DevRefused).detail).toContain("the CRM is down");
    expect((failed as DevRefused).status).toBe(502);
  });
});
