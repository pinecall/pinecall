// Rendered prompts: cached blocks stay byte-identical, the view follows state.

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  Agent,
  CallWorld,
  describe as describeClass,
  recalled,
  render,
  seal,
  setCall,
  tool,
  type Child,
} from "../../src/index.js";
import { PROMPT_BLOCKS, type Block, type Blocks } from "../../src/views/layout.js";
import { promptOf, showPrompt } from "../../src/views/render.js";
import ClinicaNorte from "../agent/clinica-norte.js";

const KNOWN = "+34 600 000 001";

// `Ctor.toString()` excludes the class docstring, so the loader passes the source in.
describeClass(ClinicaNorte, readFileSync(new URL("../agent/clinica-norte.tsx", import.meta.url), "utf8"));

/** A clinic agent with a call on the given channel. */
function clinica(channel = "phone"): ClinicaNorte {
  const agent = seal(new ClinicaNorte());
  setCall(agent, new CallWorld({ id: "CA_1", contact: KNOWN, from: KNOWN, channel }, () => undefined));
  return agent;
}

/** Text of the named block. */
function block(blocks: Blocks, name: string): string {
  const found = blocks.blocks.find((one) => one.name === name);
  if (found === undefined) throw new Error(`no block ${name}`);
  return found.text;
}

function names(blocks: Blocks, region?: Block["region"]): string[] {
  return blocks.blocks.filter((one) => region === undefined || one.region === region).map((one) => one.name);
}

describe("the layout", () => {
  it("is the framework's four blocks, static then dynamic, with the view last", () => {
    expect(PROMPT_BLOCKS).toEqual([
      { name: "identity", region: "static" },
      { name: "knowledge", region: "static" },
      { name: "tools", region: "static" },
      { name: "view", region: "dynamic" },
    ]);
    expect(names(promptOf(clinica()))).toEqual(["identity", "knowledge", "tools", "view"]);
  });

  it("keeps every static block byte-identical across state changes", async () => {
    const agent = clinica();
    const before = promptOf(agent);

    await agent.findPatient("Ana", KNOWN);
    await agent.freeSlots("lunes");
    await agent.book({ when: "lunes 10:00", doctor: "Ruiz" });

    const after = promptOf(agent);
    for (const name of names(before, "static")) expect(block(after, name)).toBe(block(before, name));
  });

  it("opens identity with the class docstring, then the rules, the protocols and the channel", () => {
    const identity = block(promptOf(clinica()), "identity");
    expect(identity.startsWith("Agenda de la Clínica Norte.")).toBe(true);
    expect(identity.indexOf("<rules>")).toBeLessThan(identity.indexOf("<protocols>"));
    expect(identity.indexOf("<protocols>")).toBeLessThan(identity.indexOf("<channel>"));
    expect(identity).not.toContain("<tools>");
  });

  // The runtime fills the knowledge block; the app must not send a second copy.
  it("leaves the knowledge block to the runtime, and every declared tool in tools", () => {
    const blocks = promptOf(clinica());
    expect(block(blocks, "knowledge")).toBe("");
    const tools = block(blocks, "tools");
    for (const name of ["findPatient", "freeSlots", "book", "transfer"]) {
      expect(tools).toContain(`- ${name}: `);
    }
  });
});

describe("the view", () => {
  it("flips a conditional when the state changes", async () => {
    expect(block(promptOf(clinica()), "view")).toContain("Saluda y pide nombre y teléfono");

    const agent = clinica();
    await agent.findPatient("Ana", KNOWN);

    const identified = block(promptOf(agent), "view");
    expect(identified).not.toContain("Saluda y pide nombre y teléfono");
    expect(identified).toContain("Hablas con Ana, ya en la ficha.");
    expect(identified).toContain("Pregunta para qué día quiere la cita.");
  });

  it("answers a phone call differently from a web chat once there are slots", async () => {
    const byPhone = clinica("phone");
    await byPhone.findPatient("Ana", KNOWN);
    await byPhone.freeSlots("lunes");
    expect(block(promptOf(byPhone), "view")).toContain("Ofrece como máximo dos de estas horas");

    const written = clinica("web");
    await written.findPatient("Ana", KNOWN);
    await written.freeSlots("lunes");
    expect(block(promptOf(written), "view")).toContain("Muestra hasta cinco horas");
  });

  it("is empty for a class that renders nothing at all", () => {
    /** Agenda que no dice nada de este turno. */
    class Callada extends Agent {}

    expect(block(promptOf(seal(new Callada())), "view")).toBe("");
  });

  it("puts a collapsed stretch of the call in the history, and no marker line with it", async () => {
    const agent = clinica();
    await agent.findPatient("Ana", KNOWN);
    await agent.freeSlots("lunes");
    await agent.book({ when: "lunes 10:00", doctor: "Ruiz" });

    const { history } = promptOf(agent);
    expect(history).toBe("Reservado lunes 10:00 con Ruiz.");
  });

  // No placeholder markers that could be substituted (docs/security/prompt-injection.md).
  it("writes no marker line anywhere on the printed page", async () => {
    const agent = clinica();
    await agent.findPatient("Ana", KNOWN);
    await agent.freeSlots("lunes");

    expect(showPrompt(agent)).not.toContain("<!--");
  });
});

// `remembers()` is false until the runtime returns a recall.
describe("what the agent remembers about this caller", () => {
  it("is false until the runtime has recalled something", () => {
    const agent = clinica();

    expect(agent.remembers("médico habitual")).toBe(false);
  });

  it("answers on the word a fact was filed under, and on the fact itself", async () => {
    const agent = clinica();
    await agent.findPatient("Ana", KNOWN);
    recalled(agent, ["su médico habitual es la doctora Vidal", "médico habitual"]);

    expect(agent.remembers("médico habitual")).toBe(true);
    expect(agent.remembers("la doctora Vidal")).toBe(true);
    expect(agent.remembers("alergias")).toBe(false);
    expect(block(promptOf(agent), "view")).toContain("Ofrece primero las horas de su médico habitual");
  });
});

describe("the printed page", () => {
  it("rules every block under its name and region, the history between the two regions", () => {
    const headers = showPrompt(clinica())
      .split("\n")
      .filter((line) => line.startsWith("── "));
    expect(headers).toEqual([
      "── identity (static) ──",
      "── knowledge (static) ──",
      "── tools (static) ──",
      "── history ──",
      "── view (dynamic) ──",
    ]);
  });
});

// Every tool is listed in the static `tools` block; visibility is enforced on the wire.
describe("a class with one tool and no view", () => {
  /** Agenda con preguntas frecuentes. */
  class ConUnaTool extends Agent {
    slots: string[] = [];

    /** Horas libres. */
    @tool()
    freeSlots(): string[] {
      return (this.slots = ["lunes 10:00", "lunes 11:00"]);
    }
  }

  it("declares it in the static tools block and renders an empty view", () => {
    const blocks = promptOf(seal(new ConUnaTool()));

    expect(block(blocks, "tools")).toBe("<tools>\n- freeSlots: Horas libres.\n</tools>");
    expect(block(blocks, "view")).toBe("");
  });
});

// `@render` passes the instance itself as props, not a spread, so getters and `remembers()` work.
describe("a prompt declared with @render", () => {
  /** El prompt como función del agente: los props son la instancia. */
  const SoportePrompt = ({ stage, order }: Soporte) => (
    <>
      {stage === "identify" && <p>Pide el número de pedido. Nada más hasta tenerlo.</p>}
      {order && <p>Hablas del pedido {order}.</p>}
    </>
  );

  /** Soporte de Tienda Sur. */
  @render(SoportePrompt)
  class Soporte extends Agent {
    stage = "identify";
    order?: string | undefined;
  }

  /** El mismo soporte, escrito como método. */
  class ConMetodo extends Agent {
    stage = "identify";
    order?: string | undefined;

    override render(): Child {
      return SoportePrompt(this);
    }
  }

  it("renders the block the method spelling renders, byte for byte, on the same state", () => {
    const declarado = seal(new Soporte());
    const escrito = seal(new ConMetodo());
    declarado.startIn({ stage: "resolve", order: "TS-8001" });
    escrito.startIn({ stage: "resolve", order: "TS-8001" });

    const text = block(promptOf(declarado), "view");
    expect(text).toBe("Hablas del pedido TS-8001.");
    expect(text).toBe(block(promptOf(escrito), "view"));
  });

  it("is a render() like any other, so a class with neither still renders nothing", () => {
    expect(block(promptOf(seal(new Soporte())), "view")).toContain("Pide el número de pedido");
  });

  it("refuses a class that declares both spellings, naming it and both", () => {
    const unPrompt = (): Child => <p>uno</p>;

    expect(() => {
      /** Una clase que contesta la misma pregunta dos veces. */
      @render(unPrompt)
      class Ambas extends Agent {
        override render(): Child {
          return <p>dos</p>;
        }
      }
      return Ambas;
    }).toThrow("Ambas declares both @render(unPrompt) and a render() method; two ways to answer one question — keep one");
  });
});
