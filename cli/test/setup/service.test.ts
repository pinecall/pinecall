/** `pinecall setup`'s service: the runtime's reading parsed, the shell files scanned for key names, the answers as flags, each stage's options. */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as service from "../../src/setup/service.js";
import { folder } from "../support/project.js";

const READ: service.Read = {
  machine: { system: "linux", arch: "x86_64", cores: 8, ram_gib: 32, cards: [{ name: "NVIDIA L4", memory_gib: 22.5 }], apple_silicon: false, docker: true, ollama_here: false, keys_found: ["deepgram"] },
  recommendation: {
    on: "gpu",
    budget_gib: 22.5,
    stack: { stt: "local", turn: "smart-turn", llm: "local/gemma4:12b", tts: "local", judge: "local/gemma4:12b", caller: "local/gemma4:12b" },
    candidates: [
      { model: "qwen3:30b-a3b-instruct-2507-q4_K_M", needs_gib: 18.3, fits: false, short_by_gib: 1.6, first_token_s: 0.4, message: "3/3", documents: "3/3", talk: "3/3", note: "the fastest" },
      { model: "gemma4:12b", needs_gib: 9, fits: true, short_by_gib: 0, first_token_s: 0.9, message: "3/3", documents: "3/3", talk: "3/3", note: "did everything" },
    ],
    keys: { stt: { vendor: "deepgram", variable: "DEEPGRAM_API_KEY", found: true }, llm: { vendor: "anthropic", variable: "ANTHROPIC_API_KEY", found: false }, tts: { vendor: "cartesia", variable: "CARTESIA_API_KEY", found: false } },
    notes: [],
  },
};
const VENDORS: service.Vendor[] = [
  { vendor: "anthropic", does: ["llm"], ends_turns: false, broken: null },
  { vendor: "deepgram", does: ["stt", "tts"], ends_turns: true, broken: null },
  { vendor: "cartesia", does: ["stt", "tts"], ends_turns: false, broken: null },
];

describe("the answers", () => {
  it("come from the recommendation, each stage a flag may name instead; the judge and the caller follow the thinking", () => {
    const answers = service.answersFrom(READ, { llm: "local/qwen3:30b-a3b-instruct-2507-q4_K_M", email: "ana@acme.test" });
    expect(answers).toEqual({
      stt: "local",
      turn: "smart-turn",
      llm: "local/qwen3:30b-a3b-instruct-2507-q4_K_M",
      tts: "local",
      judge: "local/gemma4:12b",
      caller: "local/gemma4:12b",
      chatOnly: false,
      email: "ana@acme.test",
    });
    expect(service.flagsOf(answers)).toEqual([
      "setup", "--yes", "--stt", "local", "--turn", "smart-turn", "--llm", "local/qwen3:30b-a3b-instruct-2507-q4_K_M", "--tts", "local",
      "--judge", "local/gemma4:12b", "--caller", "local/gemma4:12b", "--email", "ana@acme.test",
    ]);
    const same = service.answersFrom(READ, { chatOnly: true });
    expect(service.flagsOf(same)).toEqual(["setup", "--yes", "--stt", "local", "--turn", "smart-turn", "--llm", "local/gemma4:12b", "--tts", "local", "--chat-only"]);
  });

  it("refuse a turn that is not one of the three", () => {
    expect(() => service.turnOf("vad")).toThrow("--turn is one of stt, smart-turn, livekit");
    expect(service.turnOf(" LiveKit ")).toBe("livekit");
  });
});

describe("a stage's options", () => {
  it("are the measured models, marked whether they fit, then every vendor doing the stage", () => {
    const thinking = service.optionsFor("llm", READ, VENDORS);
    expect(thinking.map((one) => [one.value, one.fits])).toEqual([
      ["local/qwen3:30b-a3b-instruct-2507-q4_K_M", false],
      ["local/gemma4:12b", true],
      ["anthropic", undefined],
    ]);
    expect(thinking[0]!.hint).toContain("short by 1.6 GB");
    expect(service.optionsFor("stt", READ, VENDORS).map((one) => one.value)).toEqual(["local", "deepgram", "cartesia"]);
    expect(service.optionsFor("tts", READ, VENDORS).map((one) => one.value)).toEqual(["local", "deepgram", "cartesia"]);
  });

  it("offer the ears' own end of turn only to ears that have one", () => {
    expect(service.optionsFor("turn", READ, VENDORS, "deepgram").map((one) => one.value)).toEqual(["stt", "smart-turn", "livekit"]);
    expect(service.optionsFor("turn", READ, VENDORS, "local").map((one) => one.value)).toEqual(["smart-turn", "livekit"]);
  });
});

describe("the keys", () => {
  it("are found by name in the shell's files, and their values never read", () => {
    const home = folder();
    writeFileSync(join(home, ".zshrc"), 'export DEEPGRAM_API_KEY="dg-secret-value"\nalias ll="ls -l"\n');
    mkdirSync(join(home, ".config", "fish"), { recursive: true });
    writeFileSync(join(home, ".config", "fish", "config.fish"), "set -gx CARTESIA_API_KEY ck-secret\n");
    const found = service.keysInShellFiles(home);
    expect(found).toEqual({ DEEPGRAM_API_KEY: "~/.zshrc", CARTESIA_API_KEY: "~/.config/fish/config.fish" });
    expect(JSON.stringify(found)).not.toContain("secret");
    expect(service.whereKeyIs("DEEPGRAM_API_KEY", { DEEPGRAM_API_KEY: "x" }, found)).toBe("in the environment");
    expect(service.whereKeyIs("CARTESIA_API_KEY", {}, found)).toContain("in ~/.config/fish/config.fish, not exported");
    expect(service.whereKeyIs("ANTHROPIC_API_KEY", {}, found)).toBe("not set: the runtime asks for it");
  });
});
