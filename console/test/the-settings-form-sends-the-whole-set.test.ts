// The Settings form round-trips a corner's whole config: it opens on what is set and saves all of it.

import { describe, expect, it } from "vitest";

import { languagesWith } from "../src/screens/settings/language";
import { configOf, knobOf, typedOf, wordOf } from "../src/screens/settings/typed";

const VENDORS = new Set(["anthropic", "deepgram", "elevenlabs", "cartesia"]);

describe("a model knob, read as two picks", () => {
  it("reads a vendor, a vendor with its model, and a bare model on the vendor in use", () => {
    expect(knobOf("deepgram", VENDORS)).toEqual({ vendor: "deepgram", model: "" });
    expect(knobOf("anthropic/claude-haiku-5-5", VENDORS)).toEqual({ vendor: "anthropic", model: "claude-haiku-5-5" });
    expect(knobOf("claude-sonnet-5", VENDORS)).toEqual({ vendor: "", model: "claude-sonnet-5" });
    expect(knobOf(null, VENDORS)).toEqual({ vendor: "", model: "" });
  });

  it("writes the same three forms back, and nothing when neither was picked", () => {
    expect(wordOf({ vendor: "deepgram", model: "" })).toBe("deepgram");
    expect(wordOf({ vendor: "anthropic", model: "claude-opus-5" })).toBe("anthropic/claude-opus-5");
    expect(wordOf({ vendor: "", model: "claude-sonnet-5" })).toBe("claude-sonnet-5");
    expect(wordOf({ vendor: "", model: "" })).toBe("");
  });
});

describe("the form opened on a corner", () => {
  it("folds tts_model into the speaking pick, since it wins on the wire", () => {
    const typed = typedOf({ tts: "elevenlabs", tts_model: "eleven_multilingual_v2", voice: "carolina" }, VENDORS);

    expect(typed.tts).toEqual({ vendor: "elevenlabs", model: "eleven_multilingual_v2" });
    expect(typed.voice).toBe("carolina");
  });

  it("opens on the instruction when the greeting is one, and on the words otherwise", () => {
    expect(typedOf({ greeting: { reply: "greet them" } }, VENDORS).opening).toBe("reply");
    expect(typedOf({ greeting: { say: "Buenos días." } }, VENDORS).opening).toBe("say");
    expect(typedOf({}, VENDORS).opening).toBe("say");
  });

  it("lists the bases as rows, with the three numbers the corner set", () => {
    expect(typedOf({ bases: [{ base: "clinica", k: 4, mode: "tool", min_score: 0.5 }, { base: "tarifas" }] }, VENDORS).bases).toEqual([
      { base: "clinica", k: "4", mode: "tool", min_score: "0.5" },
      { base: "tarifas", k: "", mode: "retrieved", min_score: "" },
    ]);
  });
});

describe("what the form sends", () => {
  it("is the whole set, every pick as one wire word, and tts_model never", () => {
    const typed = typedOf({ tts_model: "eleven_multilingual_v2", memory: { remember: ["allergies"], forget: [] } }, VENDORS);
    typed.stt = { vendor: "deepgram", model: "nova-3" };
    typed.llm = { vendor: "", model: "" };
    typed.tts = { vendor: "elevenlabs", model: "eleven_v3_conversational" };
    typed.voice = "mateo";
    typed.say = "Clínica Norte, ¿en qué le ayudo?";
    typed.endpointing_ms = "900";
    typed.bases = [{ base: "clinica", k: "4", mode: "retrieved", min_score: "" }];

    expect(configOf(typed, false, {})).toEqual({
      stt: "deepgram/nova-3",
      tts: "elevenlabs/eleven_v3_conversational",
      voice: "mateo",
      greeting: { say: "Clínica Norte, ¿en qué le ayudo?" },
      turn: { endpointing_ms: 900 },
      memory: { remember: ["allergies"], forget: [] },
      bases: [{ base: "clinica", k: 4 }],
    });
  });

  // Three states on screen, two on the wire: unset inherits from the level below.
  it("sends a recording nobody set as nothing at all, and one turned off as false", () => {
    const untouched = typedOf({}, VENDORS);
    expect(untouched.record).toBe("");
    expect(configOf(untouched, false, {}).record).toBeUndefined();

    const off = typedOf({ record: false }, VENDORS);
    expect(off.record).toBe("off");
    expect(configOf(off, false, {}).record).toBe(false);

    const on = typedOf({ record: true }, VENDORS);
    expect(on.record).toBe("on");
    expect(configOf(on, false, {}).record).toBe(true);
  });

  // 0 means no limit; unset falls back to the runtime default.
  it("sends a voice call's limit nobody set as nothing, and no limit as zero", () => {
    const untouched = typedOf({}, VENDORS);
    expect(configOf(untouched, false, {}).max_duration_s).toBeUndefined();
    expect(configOf(typedOf({ max_duration_s: 0 }, VENDORS), false, {}).max_duration_s).toBe(0);
    expect(configOf(typedOf({ max_duration_s: 900 }, VENDORS), false, {}).max_duration_s).toBe(900);
  });

  // Unset pins no language: each vendor runs its own default.
  it("sends a language nobody set as nothing, and one picked as its tag", () => {
    expect(configOf(typedOf({}, VENDORS), false, {}).language).toBeUndefined();

    const picked = typedOf({}, VENDORS);
    picked.language = "es";
    expect(configOf(picked, false, {}).language).toBe("es");

    const cleared = typedOf({ language: "es" }, VENDORS);
    cleared.language = "";
    expect(configOf(cleared, false, {}).language).toBeUndefined();
  });

  it("keeps a language set from the terminal that is not on the list, and offers it first", () => {
    const typed = typedOf({ language: "pt-BR" }, VENDORS);
    expect(configOf(typed, false, {}).language).toBe("pt-BR");
    expect(languagesWith("pt-BR")[0]).toBe("pt-BR");
    expect(languagesWith("es")).toEqual(languagesWith(""));
  });

  it("sends of an attachment only what was picked: no k, no mode and no floor unless they were", () => {
    const typed = typedOf({}, VENDORS);
    typed.bases = [
      { base: "clinica", k: "", mode: "retrieved", min_score: "" },
      { base: "tarifas", k: "4", mode: "tool", min_score: "0.5" },
    ];

    expect(configOf(typed, false, {}).bases).toEqual([{ base: "clinica" }, { base: "tarifas", k: 4, mode: "tool", min_score: 0.5 }]);
  });

  it("sends the instruction and not the words when the opening is the model's", () => {
    const typed = typedOf({}, VENDORS);
    typed.opening = "reply";
    typed.reply = "greet them and ask what they need";
    typed.say = "left over from before";

    expect(configOf(typed, false, {}).greeting).toEqual({ reply: "greet them and ask what they need" });
  });

  it("carries the corner's other fields over for a key that opens words alone", () => {
    const standing = { voice: "carolina", language: "es", llm: "anthropic/claude-haiku-5-5", greeting: { say: "Buenas." }, bases: [{ base: "clinica", k: 4 }] };
    const typed = typedOf(standing, VENDORS);
    typed.say = "Clínica Norte, buenos días.";
    typed.knowledge = "# Horario\nDe 9 a 20.";
    typed.llm = { vendor: "", model: "" };

    expect(configOf(typed, true, standing)).toEqual({
      voice: "carolina",
      language: "es",
      llm: "anthropic/claude-haiku-5-5",
      greeting: { say: "Clínica Norte, buenos días." },
      knowledge: "# Horario\nDe 9 a 20.",
      bases: [{ base: "clinica", k: 4 }],
    });
  });
});

describe("a model's temperature and a plugin's own", () => {
  it("opens on what the corner set and sends it back, the options as an object", () => {
    const typed = typedOf({ llm: "openai/gpt-5.4-mini", temperature: 0.3, llm_builds: "responses.LLM", llm_options: { use_websocket: true } }, VENDORS);
    typed.plugins.stt = { builds: "", options: '{ "eot_timeout_ms": 900 }' };

    expect(typed.temperature).toBe("0.3");
    expect(configOf(typed, false, {})).toMatchObject({
      temperature: 0.3,
      llm_builds: "responses.LLM",
      llm_options: { use_websocket: true },
      stt_options: { eot_timeout_ms: 900 },
    });
  });

  it("refuses options that are not a JSON object, in a sentence", () => {
    const typed = typedOf({}, VENDORS);
    typed.plugins.tts = { builds: "", options: "speed=1.1" };

    expect(() => configOf(typed, false, {})).toThrow("The TTS plugin's options are not a JSON object");
  });
});

describe("the model the calls are judged on", () => {
  it("opens on the corner's judge and its own server, and sends both back", () => {
    const standing = { judge: "openai/qwen3-32b", judge_options: { base_url: "http://gpu:8000/v1" } };
    const typed = typedOf(standing, new Set([...VENDORS, "openai"]));

    expect(typed.judge).toEqual({ vendor: "openai", model: "qwen3-32b" });
    expect(configOf(typed, false, {})).toMatchObject(standing);
  });

  it("sends nothing when no judge is picked, so the org's choice stands", () => {
    const config = configOf(typedOf({}, VENDORS), false, {});

    expect([config.judge, config.judge_builds, config.judge_options]).toEqual([undefined, undefined, undefined]);
  });

  it("keeps the corner's judge when the class declares one", () => {
    const standing = { judge: "anthropic/claude-haiku-5-5" };
    const typed = typedOf(standing, VENDORS);
    typed.judge = { vendor: "openai", model: "gpt-5.4-mini" };

    expect(configOf(typed, false, standing, new Set(["judge"])).judge).toBe("anthropic/claude-haiku-5-5");
  });
});

describe("a setting the class declares", () => {
  it("is sent as the corner had it, whatever the form holds, so the save changes nothing the class wins", () => {
    const standing = { voice: "carolina", tts: "elevenlabs", llm: "anthropic/claude-haiku-5-5", temperature: 0.2 };
    const typed = typedOf(standing, VENDORS);
    typed.voice = "mateo";
    typed.llm = { vendor: "openai", model: "gpt-5.4-mini" };
    typed.temperature = "0.9";
    typed.language = "es";

    expect(configOf(typed, false, standing, new Set(["voice", "llm"]))).toMatchObject({
      voice: "carolina",
      tts: "elevenlabs",
      llm: "anthropic/claude-haiku-5-5",
      temperature: 0.2,
      language: "es",
    });
  });
});

describe("how a call opens, ends and is cut", () => {
  it("keeps the turn's knobs the form does not change, and sends the two confidences it now shows", () => {
    const standing = { turn: { endpointing_ms: 900, eot_threshold: 0.8, eager_eot_threshold: 0.5 } };
    const typed = typedOf(standing, VENDORS);
    typed.min_interruption_words = "3";

    expect(typed.eot_threshold).toBe("0.8");
    expect(configOf(typed, false, standing).turn).toEqual({ endpointing_ms: 900, eot_threshold: 0.8, eager_eot_threshold: 0.5, min_interruption_words: 3 });
  });

  it("lets the model improvise with no instruction, and an opening the caller may cut short", () => {
    const typed = typedOf({ greeting: { reply: "" } }, VENDORS);

    expect(typed.opening).toBe("reply");
    typed.interruptible = true;
    expect(configOf(typed, false, {}).greeting).toEqual({ reply: "", allow_interruptions: true });
  });

  it("reads and sends the three ways the model may hang up", () => {
    expect(typedOf({}, VENDORS).hangs_up).toBe("never");
    expect(typedOf({ hangup: { when: "" } }, VENDORS).hangs_up).toBe("any");
    const when = typedOf({ hangup: { when: "the caller says goodbye" } }, VENDORS);
    expect(when.hangs_up).toBe("when");
    expect(configOf(when, false, {}).hangup).toEqual({ when: "the caller says goodbye" });
    when.hangs_up = "never";
    expect(configOf(when, false, {}).hangup).toBeUndefined();
  });

  it("sends who ends the turn, and keeps it as the corner had it when the class declares the ears", () => {
    const typed = typedOf({ end_of_turn: "stt" }, VENDORS);
    typed.end_of_turn = "smart-turn";

    expect(configOf(typed, false, {}).end_of_turn).toBe("smart-turn");
    expect(configOf(typed, false, { end_of_turn: "stt" }, new Set(["stt"])).end_of_turn).toBe("stt");
  });
});
