// Criterio 2 del hito, clavado por un test: cada bloque estático es byte a byte el mismo en los tres
// estados capturados, y la view cambia en los tres. El orden nunca se reordena: los bloques
// estáticos · la historia · la view, que es toda la región dinámica y lo último que lee el modelo
// — el orden que el KV-cache del proveedor premia (docs/decisions/prompt-blocks.md).

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import {
  CallWorld,
  describe as describeClass,
  promptOf,
  seal,
  setCall,
  showPrompt,
  toolNamed,
  type Blocks,
} from "@pinecall/agents";

import ClinicaNorte from "../agent.js";

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));
const SOURCE = readFileSync(here("../agent.tsx"), "utf8");
const STATES = JSON.parse(readFileSync(here("./prompts/states.json"), "utf8")) as {
  state: Record<string, unknown>;
}[];
// El fichero de goldens del diseño, el mismo que lee `pinecall prompt --state test/choose.json`.
const CASES = JSON.parse(readFileSync(here("./choose.json"), "utf8")) as {
  state: Record<string, unknown>;
}[];

describeClass(ClinicaNorte, SOURCE);

/** El agente en el estado N del fichero, como lo pone `pinecall prompt --case N`. */
function at(index: number): ClinicaNorte {
  const agent = fresh();
  // `startIn` y no `restore`, que es lo que hace el CLI: un caso nombra los campos de los que
  // trata y ninguno más, así que el primero —que no habla de horas— conserva el `slots = []` de
  // la clase en vez de quedarse sin él.
  agent.startIn(STATES[index]!.state);
  return agent;
}

// Una instancia con una llamada a la que contestar, que es lo que `pinecall prompt` le da: un
// `promptOf()` puede leer `this.call`, y una página sobre una llamada que no existe no sería la
// página del prompt. Por la web y con voz, que es lo que `pinecall prompt --channel web` imprime.
function fresh(): ClinicaNorte {
  const agent = seal(new ClinicaNorte());
  setCall(agent, new CallWorld({ id: "", contact: "", channel: "web" }, () => undefined));
  return agent;
}

/** El texto de un bloque, por nombre. */
function block(blocks: Blocks, name: string): string {
  const found = blocks.blocks.find((one) => one.name === name);
  if (found === undefined) throw new Error(`no hay bloque ${name}`);
  return found.text;
}

describe("los bloques del prompt", () => {
  it("mantiene cada bloque estático idéntico en los tres estados", () => {
    const rendered = STATES.map((_, index) => promptOf(at(index)));

    for (const name of ["identity", "knowledge", "tools"]) {
      for (const one of rendered) expect(block(one, name)).toBe(block(rendered[0]!, name));
    }
    // Y no está vacío: un prefijo vacío también sería "idéntico" y no probaría nada.
    expect(block(rendered[0]!, "identity")).toContain("recepción de Clínica Norte");
  });

  it("cambia la view en cada uno de los tres", () => {
    const dynamics = STATES.map((_, index) => block(promptOf(at(index)), "view"));

    expect(new Set(dynamics).size).toBe(STATES.length);
    expect(dynamics[0]).toContain("Saluda y pide nombre");
    expect(dynamics[1]).toContain("Ana García");
    expect(dynamics[2]).toContain("SMS");
  });

  it("imprime los bloques en su único orden: los estáticos, la historia y la view al final", () => {
    const headers = showPrompt(at(1))
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

  // Las capturas se reescriben a mano y a propósito: `CAPTURE=1 pnpm test` las vuelve a grabar
  // cuando la clase cambió de verdad —una descripción de tool, un bloque—, y el diff de git es la
  // revisión. Sin la variable, el test compara y no escribe nada.
  it("coincide con lo capturado, para que las capturas no se pudran", () => {
    for (const [index] of STATES.entries()) {
      const rendered = `${showPrompt(at(index))}\n`;
      if (process.env["CAPTURE"]) writeFileSync(here(`./prompts/state-${index}.txt`), rendered);
      const captured = readFileSync(here(`./prompts/state-${index}.txt`), "utf8");
      expect(rendered).toBe(captured);
    }
  });

  // La puerta del servidor que exigía el sí se quitó (2026-09-06) y vuelve cuando un milestone la
  // necesite; la declaración viaja igual en el wire, y eso es lo que la clase aporta y se prueba aquí.
  it("declara book como irreversible, con un recibo y no una pregunta", () => {
    // La plataforma lee el `confirm` DESPUÉS de que la herramienta corrió, así que una pregunta
    // ahí se oye cuando ya está hecha. docs/writing-an-agent.md.
    const book = toolNamed(at(1), "book");

    expect(book?.spec.side_effect).toBe("irreversible");
    expect(book?.spec.confirm).toContain("Reservado:");
    expect(book?.spec.confirm).not.toContain("¿");
  });
});

// Las horas sobre la mesa las pone la misma view, en cuanto freeSlots vuelve con ellas: son parte
// de lo que hay que decir en este turno y no un bloque aparte que el modelo lea antes.
describe("las horas sobre la mesa", () => {
  it("no están hasta que freeSlots vuelve, y entonces van en la view con qué hacer con ellas", async () => {
    const agent = at(0);
    expect(block(promptOf(agent), "view")).not.toContain("Horas libres, en orden:");

    agent.startIn({ ...STATES[0]!.state, stage: "choose", patient: { name: "Ana García", phone: "+34 600 000 001" } });
    await agent.freeSlots("martes", "medicina de familia");

    const dynamic = block(promptOf(agent), "view");
    expect(agent.slots.length).toBeGreaterThan(0);
    expect(dynamic).toContain("Horas libres, en orden:");
    expect(dynamic).toContain(agent.slots[0]!.when);
    expect(dynamic).toContain("de estas horas");
  });
});

describe("un caso de goldens nombra unos campos y calla los demás", () => {
  it("rinde el primer caso de choose.json, que no habla de horas", () => {
    // El caso está en `choose` y no menciona `slots`: la clase le dio `[]` y la vista lee
    // `slots.length`. Con `restore` ese campo llegaba borrado y la vista moría en el CLI antes de
    // imprimir nada — este test es esa llamada, sin terminal.
    const agent = fresh();
    agent.startIn(CASES[0]!.state);

    expect(block(promptOf(agent), "view")).toContain("pregúntale para qué día quiere cambiarla");
  });
});

// La clase y la vista son dos sitios donde se dice la misma regla, y durante un día no la dijeron
// igual: el docstring mandaba consultar SIEMPRE el día que nombra el paciente y la vista, sin horas
// sobre la mesa, mandaba preguntar por el día — y Haiku sigue a la vista. Este test es el clavo.
describe("la clase y la vista dicen lo mismo sobre el día que nombra el paciente", () => {
  it("repite en la vista la regla que freeSlots lleva en su docstring", () => {
    const agent = fresh();
    agent.startIn(CASES[0]!.state);
    const dynamic = block(promptOf(agent), "view");

    expect(toolNamed(agent, "freeSlots")?.spec.description).toContain("EN CUANTO tengas las dos cosas");
    expect(dynamic).toContain("consulta SIEMPRE la agenda de ese día");
    // Y la vista sigue diciendo qué hacer cuando todavía no ha nombrado ningún día: son dos
    // ramas, no una regla que sustituye a la otra.
    expect(dynamic).toContain("todavía no ha nombrado ningún día");
  });

  // El ORDEN de las dos ramas es la regla, no el estilo: la última frase de la región dinámica es
  // la que haiku ejecuta. Con la pregunta al final tomaba la pregunta aunque el paciente acabase
  // de nombrar el martes, y el golden volvía "ran no tool at all". La acción va última.
  it("deja la acción al final y la pregunta antes", () => {
    const agent = fresh();
    agent.startIn(CASES[0]!.state);
    const dynamic = block(promptOf(agent), "view");

    expect(dynamic.indexOf("todavía no ha nombrado ningún día")).toBeLessThan(
      dynamic.indexOf("consulta SIEMPRE la agenda de ese día"),
    );
  });
});

// El 2026-09-08 `no-reserva-antes-del-si` reservó en dos de cada cinco corridas sobre haiku: con
// horas sobre la mesa la vista terminaba en cómo ofrecerlas y no decía nada del turno siguiente,
// que es siempre el paciente eligiendo. El único «espera un sí explícito» estaba en el prefijo
// estático, en genérico, y nada en el prompt dice que reservar sea irreversible. Este test es el
// clavo: la regla se dice donde el modelo decide, y `book` la repite en su docstring.
describe("con horas sobre la mesa, elegir una no la reserva", () => {
  it("manda repetir la hora entera y esperar el sí, en la vista y en el docstring de book", () => {
    const agent = at(1);
    const dynamic = block(promptOf(agent), "view");

    expect(dynamic).toContain("todavía no la reserva");
    expect(dynamic).toContain("pregúntale si se la confirmas");
    expect(dynamic).toContain("solo después de que te haya dicho que sí");
    expect(toolNamed(agent, "book")?.spec.description).toContain("NO es todavía ese sí");
  });

  it("calla la regla cuando no hay ninguna hora sobre la mesa", () => {
    const agent = fresh();
    agent.startIn(CASES[0]!.state);

    expect(block(promptOf(agent), "view")).not.toContain("todavía no la reserva");
  });
});

// 2026-09-11: `no-inventa-horas-de-un-dia-sin-agenda` llamaba a freeSlots("domingo"), recibía la
// lista vacía y no decía nunca la palabra domingo. El estado volvía a ser el de antes de mirar
// —`slots` vacío, fase `choose`— y la vista repetía «¿para qué día quiere cambiarla?». El campo es
// lo que distingue no haber mirado de haber mirado y no haber nada.
describe("un día que se miró y volvió vacío se queda en el estado", () => {
  it("nombra el día en la vista, en vez de volver a pedir un día", () => {
    const agent = fresh();
    agent.startIn({
      stage: "choose",
      patient: { id: "p-1041", name: "Ana García", phone: "+34 600 000 001", cita: "jueves a las diez", doctor: "la doctora Vidal" },
      slots: [],
      dayWithNoHours: "domingo",
    });
    const dynamic = block(promptOf(agent), "view");

    expect(dynamic).toContain("agenda del domingo");
    expect(dynamic).not.toContain("todavía no ha nombrado ningún día");
  });

  it("sigue pidiendo el día cuando todavía no se ha mirado ninguno", () => {
    const agent = fresh();
    agent.startIn(CASES[0]!.state);

    expect(block(promptOf(agent), "view")).toContain("todavía no ha nombrado ningún día");
  });
});
