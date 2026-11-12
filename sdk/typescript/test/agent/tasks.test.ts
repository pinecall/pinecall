// A task: what a tool asks the caller for, the tool it is given with, and what its check makes of the answer.

import { describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { agent } from "../../src/agent/declaring.js";
import { askingFor, GetEmail, GetName, GetPhone, givenWith, givingTool, task, tasksOf } from "../../src/agent/tasks.js";
import { DeclarationRefused } from "../../src/agent/tools.js";

describe("a task", () => {
  it("is given with a tool named after it, every field a required string", () => {
    expect(givenWith(GetEmail)).toBe("give_email");
    expect(givingTool(GetName)).toMatchObject({
      name: "give_name",
      parameters: { type: "object", properties: { first: { type: "string" }, last: { type: "string" } }, required: ["first", "last"] },
    });
  });

  it("tells the model what to ask for, how, and the tool to give it with", () => {
    expect(askingFor(GetEmail)).toBe(
      "This is not done yet: it needs the caller's email address. Ask the caller for it now. Spell it back to them letter by letter and wait for a yes. Then call give_email.",
    );
  });

  it("is refused without a name a tool can carry, what it asks, its fields or its check", () => {
    const whole = { name: "plate", asks: "the car's plate", fields: { plate: "The plate." }, check: ({ plate }: { plate: string }) => plate };
    expect(task(whole).name).toBe("plate");
    expect(() => task({ ...whole, name: "Car Plate" })).toThrow(DeclarationRefused);
    expect(() => task({ ...whole, asks: "" })).toThrow(/says what it asks for/);
    expect(() => task({ ...whole, fields: {} as { plate: string } })).toThrow(/names what the model gives/);
    expect(() => task({ ...whole, check: undefined as never })).toThrow(/has a check/);
  });

  it("is declared by its class, in its tasks", () => {
    @agent({ tasks: [GetEmail, GetPhone] })
    class Books extends Agent {}
    @agent({ tasks: ["email"] as never })
    class Wrong extends Agent {}
    expect(tasksOf(Books)).toEqual([GetEmail, GetPhone]);
    expect(tasksOf(Agent)).toEqual([]);
    expect(() => tasksOf(Wrong)).toThrow(/tasks is a list of tasks/);
  });
});

describe("the tasks that come with the package", () => {
  it("GetEmail lowercases an address and refuses what is none", () => {
    expect(GetEmail.check({ email: " Ana@Example.com " })).toBe("ana@example.com");
    expect(() => GetEmail.check({ email: "ana at example dot com" })).toThrow(/is not an email address/);
  });

  it("GetPhone keeps the digits, and the plus of a country code", () => {
    expect(GetPhone.check({ number: "+1 (415) 555-0142" })).toBe("+14155550142");
    expect(GetPhone.check({ number: "415 555 0142" })).toBe("4155550142");
    expect(() => GetPhone.check({ number: "555" })).toThrow(/is not a phone number/);
  });

  it("GetName wants both names", () => {
    expect(GetName.check({ first: " Ana ", last: "Lopez" })).toEqual({ first: "Ana", last: "Lopez" });
    expect(() => GetName.check({ first: "Ana", last: " " })).toThrow(/Both names are needed/);
  });
});
