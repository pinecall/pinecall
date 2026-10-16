// `@tool({ stage })`: shorthand for visibility, and what it rejects.
import { describe, expect, it } from "vitest";

import { Agent, seal, tool, toolNamed, visibleTools, withAuthor, type Stages } from "../../src/index.js";

/** Una recepción de tres fases, escrita como la escribe un tenant. */
class ThreePhases extends Agent {
  stage: Stages<"identify" | "choose" | "book"> = "identify";
  slots: string[] = [];

  /** Busca al paciente. */
  @tool({ stage: "identify" })
  findPatient(): void {
    this.stage = "choose";
  }

  /** Horas libres de un día. */
  @tool({ stage: ["choose", "book"] })
  freeSlots(): void {
    this.slots = ["martes 16:00"];
    this.stage = "book";
  }

  /** Reserva la hora que el paciente eligió. */
  @tool({ stage: "book", when: (s) => s.slots.length > 0 })
  book(): void {}

  /** Pasa la llamada a recepción. */
  @tool()
  transfer(): void {}
}

/** Una clase sin fases: `stage` en una tool suya no tiene nada a lo que preguntar. */
class NoStages extends Agent {
  patient?: string;

  /** Reserva la hora. */
  // With no `stage` field, `StageOf<NoStages>` is never.
  // @ts-expect-error a stage on a class that declares none
  @tool({ stage: "book" })
  book(): void {}
}

function names(agent: object): string[] {
  return visibleTools(agent).map((spec) => spec.name);
}

describe("a tool that names its stages", () => {
  it("is visible in the stage the state names, and gone in every other", () => {
    const agent = seal(new ThreePhases());
    expect(names(agent)).toEqual(["findPatient", "transfer"]);

    agent.findPatient();

    expect(names(agent)).toEqual(["freeSlots", "transfer"]);
  });

  it("takes a list of stages, and is there in each of them", () => {
    const agent = seal(new ThreePhases());
    agent.findPatient();
    expect(names(agent)).toContain("freeSlots");

    agent.freeSlots();

    expect(names(agent)).toContain("freeSlots");
    expect(names(agent)).toEqual(["freeSlots", "book", "transfer"]);
  });

  it("with a when beside it is visible only where both hold", () => {
    const agent = seal(new ThreePhases());
    // State writes need an author outside a tool.
    withAuthor("test", () => (agent.stage = "book"));
    expect(names(agent)).not.toContain("book");

    withAuthor("test", () => (agent.slots = ["martes 16:00"]));

    expect(names(agent)).toContain("book");
  });

  it("with neither stage nor when is there in every stage", () => {
    const agent = seal(new ThreePhases());
    for (const stage of ["identify", "choose", "book"] as const) {
      withAuthor("test", () => (agent.stage = stage));
      expect(names(agent)).toContain("transfer");
    }
  });

  it("lowers to the one visibility there is: a when, and nothing the registry had to learn", () => {
    const declared = toolNamed(seal(new ThreePhases()), "findPatient");

    expect(typeof declared?.options.when).toBe("function");
    expect(declared?.options.stage).toBe("identify");
    // Stages are client-side only; the wire only sees the resulting tool list.
    expect(Object.keys(declared?.spec ?? {})).not.toContain("stage");
  });
});

describe("a stage on a class that declares none", () => {
  it("is refused when the class is read, with the sentence that says what to write", () => {
    expect(() => seal(new NoStages()).tools()).toThrowError(
      /stage names a value of this agent's own stage field, and NoStages declares none/,
    );
  });
});
