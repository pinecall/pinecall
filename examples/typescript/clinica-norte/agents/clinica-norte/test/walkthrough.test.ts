// El recorrido entero contra el gateway que no existe: identificar, ofrecer, reservar, y el "no".
// El paseo por la terminal (`pinecall chat`) es de la tarjeta de integración; esto es su equivalente
// en proceso: las mismas cuatro fases, los mismos tool.result, sin teclado y sin modelo.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "@pinecall/agents/client";
import { FakeGateway } from "@pinecall/agents/client/testing";
import { mount, type Mounted } from "@pinecall/agents";

import ClinicaNorte from "../agent.js";
import { hourOf, REFUSED_HOUR, type Slot } from "../agenda.js";

const KEY = "pk_test";
const SLUG = "clinica-norte";
const CALL = "CA_chat_1";
const ANA = "+34 600 000 001";
const SOURCE = readFileSync(fileURLToPath(new URL("../agent.tsx", import.meta.url)), "utf8");

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  // Una tool que falla llega al modelo como tool.result y a la app como error; aquí se lee el cable,
  // así que el lado de la app se calla en vez de imprimirse.
  pc.onErrors(() => {});
  mounted = mount(ClinicaNorte, { pc, source: SOURCE, slug: SLUG });
  await pc.connect();
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

/** Dejar que se asiente todo lo que el socket empezó: el bridge lo espera todo, nadie cronometra. */
async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function calls(name: string, args: Record<string, unknown>): void {
  gateway.emit(SLUG, CALL, "tool.call", { call_id: `t-${name}`, name, arguments: args });
}

function results(): Record<string, unknown>[] {
  return gateway.commandsOf("tool.result").map((command) => command.data);
}

function offered(): string[] {
  const sent = gateway.commandsOf("tools.set").at(-1)?.data["tools"] as { name: string }[];
  return sent.map((tool) => tool.name);
}

it("recorre identificar, ofrecer y reservar, y dice que no cuando la agenda dice que no", async () => {
  gateway.emit(SLUG, CALL, "call.started", {
    channel: "web",
    direction: "inbound",
    from: "web_ana",
    to: SLUG,
    caller: null,
    started_at: Date.now() / 1000,
  });
  await settled();
  // Fase uno: nadie identificado, así que la única puerta abierta es preguntar quién llama.
  expect(offered()).toEqual(["findPatient", "registerPatient"]);

  calls("findPatient", { name: "Ana García", phone: ANA });
  await expect.poll(results).toHaveLength(1);
  await settled();
  expect(offered()).toEqual(["freeSlots"]);

  calls("freeSlots", { day: "martes", specialty: "medicina de familia" });
  await expect.poll(results).toHaveLength(2);
  await settled();
  // El modelo ve dos horas; el estado guarda las cuatro, y por eso puede ofrecer una tercera.
  expect((results()[1]?.["output"] as Slot[]).length).toBe(2);
  const instance = mounted.instanceOf(CALL) as unknown as ClinicaNorte;
  expect(instance.slots.length).toBeGreaterThan(2);
  expect(offered()).toEqual(["freeSlots", "propose", "book"]);

  const taken = instance.slots.find((slot) => hourOf(slot.startsAt) === REFUSED_HOUR);
  calls("book", { slot: taken!.id });
  await expect.poll(results).toHaveLength(3);
  await settled();
  // El "no" llega al modelo como texto, no como una excepción, y el estado sigue sin reserva.
  expect(String(results()[2]?.["error"])).toContain("ese hueco acaba de ocuparse");
  expect(instance.booking).toBeUndefined();
  expect(offered()).toEqual(["freeSlots", "propose", "book"]);

  calls("book", { slot: instance.slots[0]!.id });
  await expect.poll(results).toHaveLength(4);
  await settled();
  expect(instance.stage).toBe("done");
  expect(offered()).toEqual([]);
  expect(gateway.commandsOf("call.log")[0]?.data["name"]).toBe("appointment.booked");

  // La view es el último bloque que se manda: lo que el modelo lee en último lugar es el turno.
  const prompt = gateway.commandsOf("prompt.set").at(-1)?.data;
  expect(prompt?.["name"]).toBe("view");
  expect(String(prompt?.["text"])).toContain("le llega un SMS");
});
