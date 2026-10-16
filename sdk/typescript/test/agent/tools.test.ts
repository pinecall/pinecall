// Tool registry: specs sent on the wire and current visibility.
import { describe, expect, it } from "vitest";

import { seal, toolNamed, visibleTools } from "../../src/index.js";
import ClinicaNorte from "./clinica-norte.js";

function clinica(): ClinicaNorte {
  return seal(new ClinicaNorte());
}

describe("visibleTools", () => {
  it("drops a tool whose when(state) no longer holds once the patient is identified", async () => {
    const agent = clinica();
    expect(agent.visibleTools().map((spec) => spec.name)).toContain("findPatient");

    await agent.findPatient("Ana", "+34 600 000 001");

    expect(agent.visibleTools().map((spec) => spec.name)).not.toContain("findPatient");
    expect(agent.visibleTools().map((spec) => spec.name)).toContain("freeSlots");
  });

  it("shows book only once there are slots to choose from", async () => {
    const agent = clinica();
    await agent.findPatient("Ana", "+34 600 000 001");
    expect(visibleTools(agent).map((spec) => spec.name)).not.toContain("book");
    await agent.freeSlots("lunes");
    expect(visibleTools(agent).map((spec) => spec.name)).toContain("book");
  });

  it("hides everything the booking closed, and keeps what has no when at all", async () => {
    const agent = clinica();
    await agent.findPatient("Ana", "+34 600 000 001");
    await agent.freeSlots("lunes");
    await agent.book({ when: "lunes 10:00", doctor: "Ruiz" });
    const visible = agent.visibleTools().map((spec) => spec.name);
    expect(visible).toEqual(["transfer"]);
  });
});

describe("the spec the wire carries", () => {
  it("names its fields the way the wire names them", () => {
    const spec = toolNamed(clinica(), "book")?.spec;
    expect(spec).toMatchObject({
      name: "book",
      description: "Reserva la hora que el paciente eligió.",
      side_effect: "irreversible",
      confirm: "Le reservo el {{slot.when}} con {{slot.doctor}}. ¿Lo confirmo?",
    });
  });

  it("declares a tool with a confirm as irreversible, and one without as read", () => {
    const agent = clinica();
    expect(toolNamed(agent, "transfer")?.spec.side_effect).toBe("read");
    expect(toolNamed(agent, "findPatient")?.spec.side_effect).toBe("read");
  });

  it("carries the announcement the tool declared, and none when it declared none", () => {
    expect(toolNamed(clinica(), "freeSlots")?.spec.announce).toBe("Un momento, miro la agenda.");
    expect(toolNamed(clinica(), "book")?.spec.announce).toBeUndefined();
  });

  it("carries the pii the tool declared", () => {
    expect(toolNamed(clinica(), "findPatient")?.spec.pii).toEqual(["name", "phone"]);
  });

  it("builds parameters as a JSON Schema object from the signature", () => {
    const spec = toolNamed(clinica(), "findPatient")?.spec;
    expect(spec?.parameters).toMatchObject({
      type: "object",
      properties: { name: {}, phone: {} },
      required: ["name", "phone"],
    });
  });
});
