// The Agent base class: fields are state, and every assignment records its author.
import { describe, expect, it } from "vitest";

import { Agent, changes, logOf, onChange, seal, tool, UnauthoredWrite } from "../../src/index.js";
import ClinicaNorte from "./clinica-norte.js";

function clinica(): ClinicaNorte {
  return seal(new ClinicaNorte());
}

describe("the agent's state", () => {
  it("emits one change with the tool as the author when a tool assigns a field", async () => {
    const agent = clinica();
    const heard: string[] = [];
    onChange(agent, (change) => heard.push(`${change.field}=${change.author}`));

    await agent.findPatient("Ana", "+34 600 000 001");

    expect(heard).toEqual(["patient=findPatient"]);
    expect(changes(agent)).toHaveLength(1);
    expect(changes(agent)[0]).toMatchObject({ seq: 1, field: "patient", prev: undefined });
    expect(agent.patient?.name).toBe("Ana");
  });

  it("refuses a field assigned outside a tool and outside a hook", () => {
    const agent = clinica();
    expect(() => {
      agent.slots = [];
    }).toThrow(UnauthoredWrite);
    expect(changes(agent)).toHaveLength(0);
  });

  it("does not record the fields the app declared before the agent was sealed", () => {
    const agent = new ClinicaNorte();
    agent.slots = [{ when: "lunes 10:00", doctor: "Ruiz" }];
    expect(changes(agent)).toHaveLength(0);
  });

  it("keeps a field assigned twice to the same value out of the log", () => {
    /** Un contador, para ver qué cuenta el log. */
    class Counter extends Agent {
      count = 0;
      /** Pone el contador en un número. */
      @tool()
      set(to: number): void {
        this.count = to;
      }
    }
    const counter = seal(new Counter());
    counter.set(1);
    counter.set(1);
    counter.set(2);
    expect(changes(counter).map((change) => change.next)).toEqual([1, 2]);
    expect(changes(counter).map((change) => change.author)).toEqual(["set", "set"]);
  });

  it("writes what the tenant logs, with the seq the log reads", async () => {
    const agent = clinica();
    await agent.findPatient("Ana", "+34 600 000 001");
    await agent.freeSlots("lunes");
    await agent.book({ when: "lunes 10:00", doctor: "Ruiz" });
    expect(logOf(agent).map((entry) => entry.name)).toEqual(["appointment.booked"]);
  });
});

// Concurrent tools must not share an author stack across awaits.
it("two tools awaiting at the same time each author their own writes", async () => {
  const one = seal(new ClinicaNorte());
  const two = seal(new ClinicaNorte());
  const [first, second] = await Promise.all([
    one.findPatient("Ana", "+34 600 000 001"),
    two.freeSlots("martes"),
  ]);
  expect(first?.name).toBe("Ana");
  expect(second).toHaveLength(3);
  expect(changes(one).map((c) => c.author)).toEqual(["findPatient"]);
  expect(changes(two).map((c) => c.author)).toEqual(["freeSlots"]);
});
