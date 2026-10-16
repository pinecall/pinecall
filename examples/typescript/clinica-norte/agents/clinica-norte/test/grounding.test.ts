// La clase declara el contrato — las tools, el render() — y nada del entorno: la voz, el modelo,
// el idioma, el saludo, las palabras, la memoria, lo sabido de memoria y la base son del mundo,
// y una clase que todavía los declara es rechazada al cargar nombrando el verbo.
// Anillo 0: sin red, sin clave, sin modelo.

import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import { Agent, optionsFor, promptOf, seal } from "@pinecall/agents";

import ClinicaNorte from "../agent.js";

const AGENT = fileURLToPath(new URL("../agent.tsx", import.meta.url));

describe("la declaración que recibe el gateway", () => {
  it("lleva las tools, y nada del entorno ni de las puertas", () => {
    const options = optionsFor(ClinicaNorte, [], new ClinicaNorte(), AGENT);

    // Una puerta es una fila de la org (`pinecall numbers import`), nunca un campo de la clase.
    expect("routes" in options).toBe(false);
    for (const field of ["voice", "llm", "stt", "language", "greeting", "says", "hears", "memory", "docs", "knowledge"]) {
      expect((options as Record<string, unknown>)[field]).toBeUndefined();
    }
  });

  // La base es de la clase sólo como campo estático: en la instancia sería estado de la llamada, y
  // el rechazo dice cómo declararla.
  it("rechaza una base nombrada en la instancia, y dice cómo declararla en la clase", () => {
    /** Un agente que nombra su base donde va el estado. */
    class EnLaInstancia extends Agent {
      constructor() {
        super();
        Object.defineProperty(this, "docs", { value: { base: "clinica-norte" }, enumerable: true });
      }
    }

    expect(() => optionsFor(EnLaInstancia, [], new EnLaInstancia(), AGENT)).toThrow("declare it as static docs = …");
  });
});

// El prompt es lo que escribió la clínica y nada más. Lo que la memoria recuerda y lo que devuelve
// la base le llegan al modelo como resultados de una herramienta, en JSON, y por eso no hay ni un
// hueco que alguien rellene después (runtime/docs/security/prompt-injection.md).
describe("la view", () => {
  it("no lleva ningún marcador, ni una palabra que no sea de la clínica", () => {
    const rendered = promptOf(seal(new ClinicaNorte()));
    const dynamic = rendered.blocks.find((block) => block.name === "view");

    expect(dynamic?.region).toBe("dynamic");
    expect(dynamic?.text).not.toContain("<!--");
    expect(dynamic?.text).toContain("Saluda y pide nombre y teléfono");
  });

  it("deja el bloque de conocimiento al gateway, que escribe en él lo que el mundo sabe de memoria", () => {
    const rendered = promptOf(seal(new ClinicaNorte()));
    const knowledge = rendered.blocks.find((block) => block.name === "knowledge");

    expect(knowledge?.region).toBe("static");
    expect(knowledge?.text).toBe("");
  });
});
