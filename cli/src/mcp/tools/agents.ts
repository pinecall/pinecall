/** The `agent`, `lexicon`, `pipeline`, `voices` and `voice_sample` tools: the agents domain, over its service. */

import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { z } from "zod";

import * as service from "../../agents/service/index.js";
import { tool, ToolRefused } from "../tool.js";
import { AGENT } from "./fields.js";

export const agent = tool({
  name: "agent",
  description: "The agent's settings — voice, models, language, greeting, memory policy, knowledge by heart: read, set, cleared, history, diff, rollback.",
  schema: {
    action: z.enum(["show", "set", "clear", "history", "diff", "rollback", "knowledge"]).describe("show reads the settings; set writes the fields named as a new version; clear takes fields out; history lists the versions; diff compares with the team's or production's; rollback brings a version back; knowledge reads or writes what the agent knows by heart"),
    agent: AGENT,
    settings: service.SettingsInput.optional().describe("`set`: the fields to set, named as `pinecall agent set` names its flags"),
    fields: z.array(z.enum(service.FIELDS)).optional().describe("`clear`: the fields to take out; every one when left out"),
    team: z.boolean().optional().describe("write the team's settings (the org's own) instead of your own"),
    against: z.enum(["team", "production"]).optional().describe("`diff`: what yours are compared with; production when left out"),
    version: z.number().int().min(1).optional().describe("`rollback`: the version to bring back"),
    text: z.string().optional().describe("`knowledge`: what the agent knows by heart, written whole; read when left out; empty takes it out"),
    note: z.string().optional().describe("a note kept with the version written"),
  },
  manual:
    "`agent` reads and writes the agent's settings in the sandbox — the voice, the models, the language, the greeting, the memory policy, what it knows by heart — each change a new version, changed without a deploy. They are your own settings unless `team` writes the team's. `history`, `diff` and `rollback` read and undo versions. A model is named as `vendor/model`, a vendor, a model, or a tier (`haiku`). `greeting` is the words, `improvise` for the model's own opening, or `improvise:…` with an instruction; `hangup` is when, in words, or `any`; `end-of-turn` is who ends the caller's turn. `temperature` is the model's; `llm-builds` and `llm-options` (and the `stt`, `tts` and `judge` twins) are a class of the vendor's plugin and its keyword arguments, run only on the org's own key for that vendor. `judge` is the model this agent's calls are judged on, named as `llm` is, over the org's (`judging`); on the org's own key for the vendor — a local model's server through `judge-options` `{\"base_url\": …}` — its evals are never billed. A field the class declares itself is listed in `fixed`, and setting it is refused naming the class.",
  handler: async (args, ctx) => {
    const options = service.WriteOptions.parse({ agent: args.agent, team: args.team === true, note: args.note });
    switch (args.action) {
      case "set":
        return (await service.setSettings(ctx, args.settings ?? {}, options)).answer;
      case "clear":
        return (await service.clearSettings(ctx, args.fields ?? [], options)).answer;
      case "history":
        return (await service.settingsHistory(ctx, args.agent, options.team)).history;
      case "diff":
        return (await service.settingsDiff(ctx, args.agent, args.against ?? "production")).diff;
      case "rollback":
        if (args.version === undefined) throw new ToolRefused("rollback takes the version to bring back: `history` lists them");
        return (await service.rollbackSettings(ctx, args.version, options)).answer;
      case "knowledge": {
        if (args.text === undefined) {
          const read = await service.readKnowledge(ctx, args.agent, options.team);
          return { agent: read.agent, knowledge: read.knowledge };
        }
        const written = await service.writeKnowledge(ctx, args.text, options);
        return { agent: written.agent, knowledge: args.text.trim() === "" ? "taken out" : `${args.text.length} characters`, version: written.version };
      }
      default:
        return (await service.showSettings(ctx, args.agent)).answer;
    }
  },
});

export const lexicon = tool({
  name: "lexicon",
  description: "The agent's words: how its voice says one (`add`), the words its ears must catch (`hear`), taking them out (`rm`), and its versions.",
  schema: {
    action: z.enum(["show", "add", "hear", "rm", "history"]).describe("show the words; add how the voice says one; hear the words the ears must catch; rm takes words out of both; history lists the versions"),
    agent: AGENT,
    word: z.string().optional().describe("`add`: the word as written"),
    say: z.string().optional().describe("`add`: how the voice says it"),
    words: z.array(z.string()).optional().describe("`hear` and `rm`: the words"),
    team: z.boolean().optional().describe("write the team's lexicon instead of your own"),
    note: z.string().optional().describe("a note kept with the version written"),
  },
  manual: "`lexicon` fixes words the voice says wrong (`add`, with how to say it) and names the words the ears must catch (`hear`): a brand, a doctor's name, a street. Each change is a version, kept without a deploy.",
  handler: async (args, ctx) => {
    const options = { agent: args.agent, team: args.team === true, note: args.note };
    if (args.action === "history") return await service.lexiconHistory(ctx, args.agent, options.team);
    if (args.action === "show") return await service.showLexicon(ctx, args.agent);
    if (args.action === "add") {
      if (args.word === undefined || args.say === undefined) throw new ToolRefused("add takes the word and how the voice says it");
      return await service.sayWord(ctx, service.SayWordInput.parse({ ...options, word: args.word, say: args.say }));
    }
    if ((args.words ?? []).length === 0) throw new ToolRefused(`${args.action} takes the words`);
    const input = service.WordsInput.parse({ ...options, words: args.words });
    return args.action === "hear" ? await service.hearWords(ctx, input) : await service.removeWords(ctx, input);
  },
});

export const pipeline = tool({
  name: "pipeline",
  description: "What the agent hears, decides and speaks with — the vendors and models of each stage — and the latency each measured.",
  schema: { agent: AGENT },
  manual: "`pipeline` reads the three stages a call runs on (ears, model, voice), which vendor and model each is, and the medians the agent's recent calls measured.",
  handler: async (args, ctx) => await service.showPipeline(ctx, args.agent),
});

export const voices = tool({
  name: "voices",
  description: "A voice vendor's voices in a language: the id an agent's voice setting takes, the name, gender and accent.",
  schema: {
    tts: z.string().optional().describe("the vendor; the gateway's own voice vendor when left out"),
    language: z.string().optional().describe("a language tag: en, es, pt-BR…"),
    country: z.string().optional().describe("only voices from this country: ES, MX, US…"),
  },
  manual: "`voices` lists the voices to choose from, the id first; set one with `agent` (`settings.voice`, and `settings.tts` for its vendor). `voice_sample` lets the person hear one first.",
  handler: async (args, ctx) => ({ voices: await service.listVoices(ctx, service.ListVoicesInput.parse(args)) }),
});

export const voiceSample = tool({
  name: "voice_sample",
  description: "Have the gateway say a line in a voice, as a call would, and save it as a WAV the person can play; with how long the vendor took.",
  schema: {
    voice: z.string().describe("the voice's id, from `voices`"),
    text: z.string().optional().describe("the words; the gateway's own line in the language when left out"),
    tts: z.string().optional().describe("the vendor; the gateway's own voice vendor when left out"),
    model: z.string().optional().describe("the vendor's model"),
    language: z.string().optional().describe("a language tag"),
  },
  manual: "`voice_sample` says a line through the vendor's own plugin and saves the WAV under the project's `.pinecall/voices/`: this server plays nothing, so the answer is the file's path, for the person to open, with the first-audio and whole-sentence times.",
  handler: async (args, ctx) => {
    const folder = join(ctx.cwd, ".pinecall", "voices");
    mkdirSync(folder, { recursive: true });
    const file = join(folder, `${args.voice.replace(/[^A-Za-z0-9_-]/g, "_")}.wav`);
    const said = await service.sampleVoice(ctx, service.SampleVoiceInput.parse(args), file);
    return { file: said.file, tts: said.tts, first_audio_ms: said.firstAudioMs, whole_sentence_ms: said.totalMs };
  },
});
