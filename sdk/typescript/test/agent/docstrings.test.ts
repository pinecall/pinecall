// Class and tool docstrings are readable at runtime.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { classDoc, describe as describeClass, methodParams, parametersOf, seal, toolNamed } from "../../src/index.js";
import { parseClassSource } from "../../src/agent/docstrings.js";
import ClinicaNorte from "./clinica-norte.js";

const source = readFileSync(new URL("./clinica-norte.tsx", import.meta.url), "utf8");

describe("docstrings at runtime", () => {
  it("reads the tool docstrings off the class with no build step at all", () => {
    const agent = seal(new ClinicaNorte());
    expect(agent.tools().map((spec) => spec.description)).toEqual([
      "Busca al paciente por nombre y teléfono. Pide los dos antes de llamarla.",
      "Horas libres de un día.",
      "Reserva la hora que el paciente eligió.",
      "Pasa la llamada a recepción.",
    ]);
  });

  it("reads the class docstring once the class is handed its own source", () => {
    describeClass(ClinicaNorte, source);
    expect(classDoc(ClinicaNorte)).toBe(
      "Agenda de la Clínica Norte. Nunca inventes una hora: las horas salen de la agenda, siempre.",
    );
    expect(seal(new ClinicaNorte()).doc()).toContain("Clínica Norte");
  });

  it("reads the parameter types out of the source the transformer will hand it", () => {
    describeClass(ClinicaNorte, source);
    expect(methodParams(ClinicaNorte, "findPatient")).toEqual([
      { name: "name", type: "string", optional: false },
      { name: "phone", type: "string", optional: false },
    ]);
  });

  it("types the parameters of findPatient as strings once the source is known", () => {
    describeClass(ClinicaNorte, source);
    const agent = seal(new ClinicaNorte());
    expect(toolNamed(agent, "findPatient")?.spec.parameters).toEqual({
      type: "object",
      properties: { name: { type: "string" }, phone: { type: "string" } },
      required: ["name", "phone"],
      additionalProperties: false,
    });
  });

  // Parameters after a type containing parens must not be lost.
  it("reads a parameter whose type has parens of its own", () => {
    const docs = parseClassSource(`
      class Desk {
        /** Waits for the row and calls back. */
        watch(id: string, onDone: (row: string) => void, tries?: number): void {}
      }
    `);

    expect(docs.methods.get("watch")?.params).toEqual([
      { name: "id", type: "string", optional: false },
      { name: "onDone", type: "(row: string) => void", optional: false },
      { name: "tries", type: "number", optional: true },
    ]);
  });

  // The model cannot supply a callback, so it is never required.
  it("takes a callback out of what the model is required to fill", () => {
    const docs = parseClassSource(`
      class Desk {
        /** Waits. */
        wait(cb: () => void): void {}
      }
    `);
    const params = docs.methods.get("wait")?.params ?? [];

    expect(params.map((param) => param.name)).toEqual(["cb"]);
    expect(parametersOf(params)).toEqual({
      type: "object",
      properties: { cb: { description: "callback" } },
      required: [],
      additionalProperties: false,
    });
  });

  it("expands an interface declared in the same file into its properties", () => {
    const docs = parseClassSource(`
      interface Slot { when: string; doctor: string; minutes?: number }
      class Desk {
        /** Books. */
        book(slot: Slot): void {}
      }
    `);

    expect(docs.methods.get("book")?.params[0]?.schema).toEqual({
      type: "object",
      properties: { when: { type: "string" }, doctor: { type: "string" }, minutes: { type: "number" } },
      required: ["when", "doctor"],
      additionalProperties: false,
    });
  });

  // Nested types are resolved within the same file.
  it("follows a nested interface of the same file one level down", () => {
    const docs = parseClassSource(`
      interface Slot { when: string }
      interface Booking { id: string; slot: Slot; tags: string[] }
      class Desk {
        /** Confirms. */
        confirm(booking: Booking): void {}
      }
    `);

    expect(docs.methods.get("confirm")?.params[0]?.schema).toEqual({
      type: "object",
      properties: {
        id: { type: "string" },
        slot: { type: "object", properties: { when: { type: "string" } }, required: ["when"], additionalProperties: false },
        tags: { type: "array", items: { type: "string" } },
      },
      required: ["id", "slot", "tags"],
      additionalProperties: false,
    });
  });

  it("reads a parameter with a default as optional, and one typed `| undefined` too", () => {
    const docs = parseClassSource(`
      class Desk {
        /** Lists. */
        list(day: string, page: number = 1, note?: string, tag: string | undefined = undefined): void {}
      }
    `);

    expect(docs.methods.get("list")?.params.map((param) => [param.name, param.optional])).toEqual([
      ["day", false],
      ["page", true],
      ["note", true],
      ["tag", true],
    ]);
  });

  // An undeclared type becomes an object described by its name.
  it("names a type it cannot see the declaration of", () => {
    const docs = parseClassSource(`
      class Desk {
        /** Pays. */
        pay(card: CreditCard): void {}
      }
    `);

    expect(docs.methods.get("pay")?.params[0]?.schema).toEqual({ type: "object", description: "CreditCard" });
  });

  it("parses with no regex over the source at all", () => {
    const parser = readFileSync(new URL("../../src/agent/docstrings.ts", import.meta.url), "utf8");

    expect(parser).not.toContain("new RegExp");
    expect(parser).not.toContain("matchAll");
    expect(parser).toContain("parseSync(");
  });
});

// The parser starts the class statement after its decorator; the JSDoc above it must still be found.
describe("a class that wears a decorator", () => {
  it("keeps the docstring written above the decorator", () => {
    const docs = parseClassSource(`
      const P = () => null;

      /** Eres el mostrador de Tienda Sur. */
      @render(P)
      export default class TiendaSur {}
    `);

    expect(docs.doc).toBe("Eres el mostrador de Tienda Sur.");
  });
});
