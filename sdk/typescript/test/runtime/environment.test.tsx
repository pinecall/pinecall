// What a class declares of its environment reaches agent.configure, and wins over the settings there.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { judge, llm, realtime, stt, voice } from "../../src/agent/decorators.js";
import { improvise } from "../../src/agent/opening.js";
import { judges, personas } from "../../src/agent/harness.js";
import ClinicaNorte from "../agent/clinica-norte.js";
import { ENVIRONMENT, declaredOnTheInstance, environmentOf } from "../../src/runtime/environment.js";
import { mount, optionsFor } from "../../src/runtime/connect.js";

const KEY = "pk_test";
const FILE = fileURLToPath(new URL("../agent/clinica-norte.tsx", import.meta.url));
const SOURCE = readFileSync(FILE, "utf8");

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

/** Recepción que fija su voz, su modelo, sus oídos, su idioma y cómo abre. */
@voice("cartesia", "a0e99841-438c-4a64-b679-ae501e7d6091", { model: "sonic-2" })
@llm("openai/gpt-5.4-mini", { builds: "responses.LLM", options: { use_websocket: true } })
@stt("soniox/stt-rt-v3", { endOfTurn: "smart-turn" })
class Fijada extends ClinicaNorte {
  static override language = "es";
  static override greeting = "Clínica Norte, buenas.";
  static override hangup = "the caller says goodbye";
  static override says = [{ word: "GSA", spoken: "G S A" }];
}

it("sends what the class declares, the plugin's options under their own names", async () => {
  mount(Fijada, { pc, source: SOURCE, file: FILE, slug: "fijada" });
  await pc.connect();
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
  const config = gateway.commandsOf("agent.configure")[0]?.data["config"] as Record<string, unknown>;
  expect(config["voice"]).toEqual({
    provider: "cartesia",
    voice_id: "a0e99841-438c-4a64-b679-ae501e7d6091",
    model: "sonic-2",
  });
  expect(config["llm"]).toEqual({
    provider: "openai",
    model: "gpt-5.4-mini",
    builds: "responses.LLM",
    options: { use_websocket: true },
  });
  expect(config["stt"]).toEqual({ provider: "soniox", model: "stt-rt-v3", end_of_turn: "smart-turn" });
  expect(config["language"]).toBe("es");
  expect(config["greeting"]).toEqual({ say: "Clínica Norte, buenas." });
  expect(config["hangup"]).toEqual({ when: "the caller says goodbye" });
  expect(config["says"]).toEqual([{ word: "GSA", spoken: "G S A" }]);
  expect(config["memory"]).toBeUndefined();
});

it("sends none of the environment for a class that declares none", () => {
  expect(environmentOf(ClinicaNorte)).toEqual({});
  const options = optionsFor(ClinicaNorte, [], new ClinicaNorte(), FILE) as Record<string, unknown>;
  for (const field of ENVIRONMENT) expect(options[field]).toBeUndefined();
});

it("keeps every slash of a model id after the vendor's", () => {
  @llm("livekit/openai/gpt-5-mini")
  class PorInferencia extends ClinicaNorte {}
  expect(environmentOf(PorInferencia).llm).toEqual({ provider: "livekit", model: "openai/gpt-5-mini" });
});

it("sends the judge's model, a local one by its server, as the declaration names it", () => {
  @judge("openai/qwen3-32b", { options: { base_url: "http://gpu:8000/v1" } })
  class JuzgadaEnCasa extends ClinicaNorte {}
  expect(environmentOf(JuzgadaEnCasa).judge).toEqual({
    provider: "openai",
    model: "qwen3-32b",
    options: { base_url: "http://gpu:8000/v1" },
  });
  expect(declaredOnTheInstance("judge")).toContain("@judge('<vendor>/<model>')");
});

it("sends the voice calls' realtime model beside the written calls' llm", () => {
  @llm("openai/gpt-6-luna")
  @realtime("xai/grok-voice-3.0", { options: { voice: "eve" } })
  class KalaVoz extends ClinicaNorte {}
  const declared = environmentOf(KalaVoz);
  expect(declared.llm).toEqual({ provider: "openai", model: "gpt-6-luna" });
  expect(declared.realtime).toEqual({ provider: "xai", model: "grok-voice-3.0", options: { voice: "eve" } });
  expect(declaredOnTheInstance("realtime")).toContain("@realtime('<vendor>/<model>')");
});

it("refuses a class that declares a model twice, by decorator and static field", () => {
  expect(() => {
    @llm("openai/gpt-5.4-mini")
    class DosVeces extends ClinicaNorte {
      static override llm = { provider: "anthropic", model: "claude-haiku-5-5" };
    }
    return DosVeces;
  }).toThrow(new DeclarationRefused("DosVeces declares both @llm(…) and a static llm; keep one"));
});

it("refuses an environment field on the instance, where it would be the call's state", () => {
  /** Recepción que dice su idioma como estado. */
  class EnEspanol extends ClinicaNorte {
    language = "es";
  }
  expect(() => optionsFor(EnEspanol, [], new EnEspanol(), FILE)).toThrow(
    "`language` is the class's, not a call's state: declare it as static language = …",
  );
  expect(declaredOnTheInstance("voice")).toContain("@voice('<vendor>', '<voice id>')");
});

it("reads an opening as words said, or the model's own with or without an instruction", () => {
  const greeted = (greeting: unknown) => {
    class Abre extends ClinicaNorte {}
    (Abre as unknown as { greeting: unknown }).greeting = greeting;
    return environmentOf(Abre).greeting;
  };
  expect(greeted(improvise)).toEqual({ reply: "" });
  expect(greeted(improvise("Saludá por el nombre"))).toEqual({ reply: "Saludá por el nombre" });
  expect(greeted(improvise("Saludá", { interruptible: true }))).toEqual({ reply: "Saludá", allowInterruptions: true });
  expect(greeted({ text: "Aviso legal…", interruptible: false })).toEqual({ say: "Aviso legal…", allowInterruptions: false });
  expect(() => greeted(42)).toThrow("a greeting is the words, as a string, or improvise");
});

it("reads hangup as when, in words, or true for whenever the model judges", () => {
  class Cuelga extends ClinicaNorte {
    static override hangup = true as const;
  }
  expect(environmentOf(Cuelga).hangup).toEqual({ when: "" });
});

/** Recepción que es dueña de sus jueces y sus personas: los interruptores en la clase, los archivos al lado. */
class Juzgada extends ClinicaNorte {
  static override judges = judges({ on: ["consent"] });
  static override personas = personas({ on: ["in-a-hurry", "interrupts"] });
}

it("sends the judges and the personas the class owns, with no folder beside it an empty own", async () => {
  mount(Juzgada, { pc, source: SOURCE, file: FILE, slug: "juzgada" });
  await pc.connect();
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
  const config = gateway.commandsOf("agent.configure")[0]?.data["config"] as Record<string, unknown>;
  expect(config["judges"]).toEqual({ on: ["consent"], own: [] });
  expect(config["personas"]).toEqual({ on: ["in-a-hurry", "interrupts"], own: [] });
});
