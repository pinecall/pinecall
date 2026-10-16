// The `── tools ──` page: the agent's current stage and the tools it shows.
import { describe, expect, it } from "vitest";

import { Agent, seal, tool, withAuthor, type Stages } from "../../src/index.js";
import { showMachine } from "../../src/serve/machine.js";

/** Una recepción de dos fases, para leer la página que el desarrollador mira. */
class TwoPhases extends Agent {
  stage: Stages<"identify" | "book"> = "identify";
  slots: string[] = [];

  /** Busca al paciente. */
  @tool({ stage: "identify" })
  findPatient(): void {}

  /** Reserva la hora que el paciente eligió. */
  @tool({ stage: "book", when: (s) => s.slots.length > 0 })
  book(): void {}

  /** Pasa la llamada a recepción. */
  @tool()
  transfer(): void {}
}

/** Una clase sin fases, para que la página no invente una. */
class NoStages extends Agent {
  /** Pasa la llamada a recepción. */
  @tool()
  transfer(): void {}
}

describe("the page a developer reads while writing the class", () => {
  it("puts the stage in the header and fills in only the tools that stage shows", () => {
    const page = showMachine(seal(new TwoPhases()));

    expect(page).toContain("── tools ── stage: identify");
    expect(page).toMatch(/● findPatient +identify/);
    expect(page).toMatch(/○ book +book/);
    expect(page).toMatch(/● transfer +always/);
  });

  it("says which of the two said no when a tool's own stage is not enough", () => {
    const agent = seal(new TwoPhases());
    withAuthor("test", () => (agent.stage = "book"));

    expect(showMachine(agent)).toMatch(/○ book +book · when\(state\) says no/);

    withAuthor("test", () => (agent.slots = ["martes 16:00"]));

    expect(showMachine(agent)).toMatch(/● book +book$/m);
  });

  it("names no stage for a class that declares none", () => {
    const page = showMachine(seal(new NoStages()));

    expect(page).toContain("── tools ──");
    expect(page).not.toContain("stage:");
  });
});
