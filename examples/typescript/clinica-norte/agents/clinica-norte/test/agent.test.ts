// La clase es una clase: cuatro fases, un estado, y una reserva que puede fallar.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it } from "vitest";
import {
  CallWorld,
  describe as describeClass,
  recalled,
  promptOf,
  runHook,
  runTool,
  seal,
  setCall,
  tool,
  toolNamed,
  type ToolDeclaration,
} from "@pinecall/agents";

import ClinicaNorte from "../agent.js";
import { agendaFor, hourOf, REFUSED_HOUR, type Slot } from "../agenda.js";

// La especialidad con la que se prueba reservar: la doctora Vidal pasa consulta todos los días
// laborables, así que hay huecos suyos el martes y el jueves, y uno a las 13:00 que la agenda
// rechaza siempre — que es el camino del "no" que este bloque necesita.
const LA_ESPECIALIDAD = "medicina de familia";

// El fuente de la clase, para que los tipos de los parámetros sobrevivan al transpilador: sin él,
// `day: string` es un argumento sin tipo y el esquema no puede decir nada de él.
const SOURCE = readFileSync(fileURLToPath(new URL("../agent.tsx", import.meta.url)), "utf8");
const ANA = "+34 600 000 001";

// La clase recibe su propio fuente una vez, como se lo dará el runner: sin él los tipos de los
// parámetros se perdieron en el transpilador y `name: string` llega al esquema como un objeto.
describeClass(ClinicaNorte, SOURCE);

let clinica: ClinicaNorte;

beforeEach(() => {
  clinica = onA("phone");
});

/** La clínica atendiendo una llamada por esa puerta: es lo que `promptOf()` lee de `this.call`. */
function onA(channel: string): ClinicaNorte {
  const agent = seal(new ClinicaNorte());
  setCall(agent, new CallWorld({ id: "CA_1", contact: ANA, from: ANA, channel }, () => undefined));
  return agent;
}

/** Llamar una tool como la llama el runtime: por su nombre, con el objeto que manda el modelo. */
function call(name: string, args: Record<string, unknown>): Promise<unknown> {
  const declaration = toolNamed(clinica, name) as ToolDeclaration;
  return runTool(clinica, declaration, args);
}

function names(): string[] {
  return clinica.visibleTools().map((spec) => spec.name);
}

/** El texto de un bloque del prompt, por nombre, en el estado en que esté la clínica. */
function block(name: string, agent: ClinicaNorte = clinica): string {
  const found = promptOf(agent).blocks.find((one) => one.name === name);
  if (found === undefined) throw new Error(`no hay bloque ${name}`);
  return found.text;
}

describe("identificar al paciente", () => {
  it("deja la ficha en el estado cuando el nombre y el teléfono cuadran", async () => {
    expect(clinica.stage).toBe("identify");
    await call("findPatient", { name: "Ana García", phone: ANA });
    expect(clinica.patient?.name).toBe("Ana García");
    expect(clinica.stage).toBe("choose");
  });

  it("no identifica a nadie cuando el nombre no es el de esa ficha", async () => {
    await call("findPatient", { name: "Otra Persona", phone: ANA });
    expect(clinica.patient).toBeUndefined();
    expect(clinica.stage).toBe("identify");
  });

  it("da de alta a quien no está en la ficha y pasa a elegir hora, sin cita previa", async () => {
    await call("findPatient", { name: "Bernardo", phone: "208 3524" });
    expect(clinica.stage).toBe("identify");
    await call("registerPatient", { name: "Bernardo", phone: "208 3524" });
    expect(clinica.patient?.name).toBe("Bernardo");
    expect(clinica.patient?.cita).toBeUndefined();
    expect(clinica.stage).toBe("choose");
    expect(block("view")).toContain("paciente nuevo");
    expect(block("view")).toContain("para qué día quiere la cita");
  });

  it("encuentra la ficha por el número desde el que se llama, sin preguntar nada", async () => {
    // El hook se corre como lo corre el runtime: lo que escribe lo firma el hook, no nadie.
    await runHook(clinica, "onCall", { id: "CA_1", contact: ANA, from: ANA, channel: "phone" });
    expect(clinica.patient?.name).toBe("Ana García");
    expect(clinica.stage).toBe("choose");
  });
});

describe("ofrecer horas", () => {
  beforeEach(async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
  });

  it("el modelo ve dos horas y el campo se las queda todas", async () => {
    const seen = (await call("freeSlots", { day: "martes", specialty: LA_ESPECIALIDAD })) as Slot[];
    expect(seen).toHaveLength(2);
    expect(clinica.slots.length).toBeGreaterThan(2);
    expect(clinica.slots[0]).toEqual(seen[0]);
  });

  it("un día sin agenda deja el estado vacío en vez de inventarse una hora", async () => {
    const seen = (await call("freeSlots", { day: "domingo", specialty: LA_ESPECIALIDAD })) as Slot[];
    expect(seen).toEqual([]);
    expect(clinica.slots).toEqual([]);
    // Sin horas sobre la mesa no hay nada que reservar: la fase vuelve a la de elegir el día.
    expect(clinica.stage).toBe("choose");
  });
});

describe("reservar", () => {
  beforeEach(async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    await call("freeSlots", { day: "martes", specialty: LA_ESPECIALIDAD });
  });

  it("una hora que la agenda rechaza deja la reserva sin hacer y lo dice", async () => {
    const taken = clinica.slots.find((slot) => hourOf(slot.startsAt) === REFUSED_HOUR);
    await expect(call("book", { slot: taken!.id })).rejects.toThrow("ese hueco acaba de ocuparse");
    expect(clinica.booking).toBeUndefined();
    expect(clinica.slot).toBeUndefined();
    expect(clinica.stage).toBe("book");
  });

  it("proponer una hora la deja sobre la mesa sin reservarla, y reservarla la retira", async () => {
    // La primera hora del martes, la misma que reserva el test de más abajo: cada instancia tiene
    // su propia agenda, así que lo que se reserva aquí no le falta a nadie.
    const free = clinica.slots[0] as Slot;
    await call("propose", { slot: free.id });
    expect(clinica.proposed).toEqual(free);
    expect(clinica.booking).toBeUndefined();
    expect(clinica.stage).toBe("book");

    await call("book", { slot: free.id });
    expect(clinica.proposed).toBeUndefined();
  });

  it("mirar otro día retira la hora propuesta, que ya no está entre las libres", async () => {
    await call("propose", { slot: clinica.slots[0]!.id });
    await call("freeSlots", { day: "jueves", specialty: LA_ESPECIALIDAD });
    expect(clinica.proposed).toBeUndefined();
  });

  it("una hora libre queda reservada, colapsa la historia y deja el hecho en el log", async () => {
    const free = clinica.slots[0] as Slot;
    await call("book", { slot: free.id });
    expect(clinica.booking?.when).toBe(free.when);
    expect(clinica.stage).toBe("done");
    expect(promptOf(clinica).history).toContain("Reservado");
    expect(await agendaFor(clinica).free(clinica.day!, LA_ESPECIALIDAD)).not.toContainEqual(free);
  });

  it("lo que una llamada reserva no le falta a la de al lado", async () => {
    // Dos modelos corren la misma golden en el mismo proceso: sin una agenda por llamada, el
    // segundo pedía la hora que el primero acababa de llevarse y la agenda le decía que no.
    const free = clinica.slots[0] as Slot;
    await call("book", { slot: free.id });

    const otra = seal(new ClinicaNorte());
    expect(await agendaFor(otra).free(clinica.day!, LA_ESPECIALIDAD)).toContainEqual(free);
  });
});

describe("las cuatro fases", () => {
  it("las herramientas visibles cambian con la fase y con nada más", async () => {
    expect(clinica.stage).toBe("identify");
    expect(names()).toEqual(["findPatient", "registerPatient"]);

    await call("findPatient", { name: "Ana García", phone: ANA });
    expect(clinica.stage).toBe("choose");
    expect(names()).toEqual(["freeSlots"]);

    await call("freeSlots", { day: "jueves", specialty: LA_ESPECIALIDAD });
    expect(clinica.stage).toBe("book");
    expect(names()).toEqual(["freeSlots", "propose", "book"]);

    await call("book", { slot: clinica.slots[0]!.id });
    expect(clinica.stage).toBe("done");
    expect(names()).toEqual([]);
  });

  it("book pide las dos cosas: la fase y horas sobre la mesa", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    await call("freeSlots", { day: "jueves", specialty: LA_ESPECIALIDAD });
    expect(names()).toContain("book");

    // La fase sigue siendo book y la tool desaparece igual: el predicado es la otra mitad.
    await call("freeSlots", { day: "domingo", specialty: LA_ESPECIALIDAD });

    expect(names()).not.toContain("book");
  });

  it("no compila una fase que la clase no nombra", () => {
    // @ts-expect-error "bok" no es una de las cuatro fases que declara el campo stage
    const misspelled: Parameters<typeof tool<ClinicaNorte>>[0] = { stage: "bok" };

    expect(misspelled).toBeDefined();
  });

  it("declara book como irreversible y propose como lectura, con la frase que el gate leerá", () => {
    const book = clinica.tools().find((spec) => spec.name === "book");
    expect(book?.side_effect).toBe("irreversible");
    // Un recibo y no una pregunta: se lee DESPUÉS de que la reserva ocurrió.
    expect(book?.confirm).toBe("Reservado: {{result.when}} con {{result.professional}}, {{result.specialty}}.");
    // Proponer no toca la agenda: el gate no tiene nada que leer antes de dejarla pasar, y por eso
    // el modelo puede llamarla en el mismo turno en que el paciente nombra la hora.
    const propose = clinica.tools().find((spec) => spec.name === "propose");
    expect(propose?.side_effect).toBe("read");
    expect(propose?.confirm).toBeUndefined();
    const find = clinica.tools().find((spec) => spec.name === "findPatient");
    expect(find?.pii).toEqual(["name", "phone"]);
  });
});

describe("la view", () => {
  const dynamic = (agent: ClinicaNorte = clinica): string => block("view", agent);

  it("pide nombre y teléfono mientras no haya paciente", () => {
    expect(dynamic()).toContain("Saluda y pide nombre y teléfono");
  });

  it("nombra la cita actual y dice qué hacer con el día, lo haya nombrado o no", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    const text = dynamic();
    expect(text).toContain("Hablas con Ana García, ya en la ficha");
    expect(text).toContain("Tiene cita el jueves a las diez");
    // Las dos ramas, porque la vista se rinde antes de que el paciente hable: si ya ha nombrado un
    // día se consulta, y si no, se le pregunta. Decir solo la segunda es lo que hacía que Haiku
    // volviera a preguntar por un día que el paciente acababa de decir.
    expect(text).toContain("consulta SIEMPRE la agenda de ese día");
    expect(text).toContain("pregúntale para qué día quiere cambiarla");
  });

  it("ofrece dos horas por teléfono y cinco por escrito, con las mismas horas en el estado", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    await call("freeSlots", { day: "martes", specialty: LA_ESPECIALIDAD });
    expect(dynamic()).toContain("como máximo dos");

    // La misma clase por la otra puerta: la llamada que atiende es lo único que cambia.
    const escrita = onA("web");
    await runTool(escrita, toolNamed(escrita, "findPatient") as ToolDeclaration, { name: "Ana García", phone: ANA });
    await runTool(escrita, toolNamed(escrita, "freeSlots") as ToolDeclaration, { day: "martes", specialty: LA_ESPECIALIDAD });
    expect(dynamic(escrita)).toContain("hasta cinco horas");
  });

  // Lo que la memoria sabe de esta paciente lo pone el runtime, y llega como palabras: `remembers`
  // es cómo lo pregunta la clase, y contesta que no mientras nadie haya recordado nada.
  it("prioriza al médico habitual solo cuando la memoria lo sabe", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    expect(dynamic()).not.toContain("médico habitual");

    recalled(clinica, ["su médico habitual es la doctora Vidal", "médico habitual"]);

    expect(dynamic()).toContain("Ofrece primero las horas de su médico habitual");
  });

  it("mientras nada está sobre la mesa manda repetir la hora, preguntar y proponerla", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    await call("freeSlots", { day: "martes", specialty: LA_ESPECIALIDAD });
    const text = dynamic();
    expect(text).toContain("todavía no la reserva");
    expect(text).toContain("Llama a book solo después de que te haya dicho que sí");
    expect(text).toContain("llama primero a propose");
    // El turno de después todavía no ha llegado: la frase que manda reservar sin volver a
    // preguntar no puede estar delante del modelo mientras el paciente no haya elegido nada.
    expect(text).not.toContain("Le estás proponiendo");
  });

  it("con una hora propuesta la nombra entera y manda reservar sin volver a preguntar", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    await call("freeSlots", { day: "martes", specialty: LA_ESPECIALIDAD });
    // Por id, que es lo único que identifica un hueco: dos a la misma hora con distinto
    // profesional son dos huecos, y una frase no sabe cuál de los dos.
    const elegida = clinica.slots[0] as Slot;
    await call("propose", { slot: elegida.id });
    const text = dynamic();
    expect(text).toContain(`Le estás proponiendo ${elegida.when} con ${elegida.professional}`);
    expect(text).toContain("llama a book con ella en ese mismo turno");
    expect(text).toContain("sin repetírsela otra vez ni volver a preguntar");
    // Y la de antes se va: las dos juntas son la contradicción que dejaba la llamada sin reserva.
    expect(text).not.toContain("todavía no la reserva");
  });

  it("cierra con el SMS cuando ya hay reserva", async () => {
    await call("findPatient", { name: "Ana García", phone: ANA });
    await call("freeSlots", { day: "viernes", specialty: LA_ESPECIALIDAD });
    await call("book", { slot: clinica.slots[0]!.id });
    expect(dynamic()).toContain("le llega un SMS");
  });
});

describe("los bloques estáticos", () => {
  // El bloque `knowledge` lo escribe el gateway con lo que el mundo dice que el agente se sabe de
  // memoria (Settings ▸ Knowledge): la app no manda nada en él.
  it("dejan el conocimiento al runtime y listan las cinco tools", () => {
    expect(block("knowledge")).toBe("");
    expect(block("identity")).toContain("Nunca inventes una hora");
    for (const name of ["findPatient", "freeSlots", "propose", "book"]) {
      expect(block("tools")).toContain(`- ${name}:`);
    }
  });

  it("tipa los parámetros del fuente que la clase recibió", () => {
    const find = clinica.tools().find((spec) => spec.name === "findPatient");
    const properties = (find?.parameters as { properties: Record<string, { type: string }> }).properties;
    expect(properties["name"]).toEqual({ type: "string" });
    expect(properties["phone"]).toEqual({ type: "string" });
  });
});
