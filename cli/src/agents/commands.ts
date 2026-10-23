/** `pinecall agent | lexicon | pipeline | voices`: what the org set over the class, its words, what it runs on, the voices to pick. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { UsageError } from "../errors.js";
import { editInEditor } from "../kit/editor.js";
import { numberOf } from "../kit/flags.js";
import { parseKeyValues } from "../kit/keyvalue.js";
import { playFile } from "../kit/player.js";
import * as render from "./render.js";
import * as service from "./service/index.js";

const AGENT = `
With nothing after it: the agent's settings as your key sees them, three corners side by side —
your own sandbox corner, the team's, and production's — a row per field, and which version each
corner is at. A corner that set nothing reads as what it falls back to.

set writes a NEW version in your own corner: what you set is yours, and a colleague's next call
does not hear it. --team writes the org's own corner instead, which every corner falls back to.
--prod writes production's, if your org lets you act there. The whole set travels with the
version it was read at, so two people saving at once never write over each other. A model knob
reads four ways — \`--llm anthropic/claude-haiku-5-5\`, \`--llm cartesia\` (a vendor), \`--llm
claude-haiku-5-5\` (a model), and \`--llm haiku\` (a tier). --realtime names the model a voice call
runs on alone, one that hears and speaks itself (\`pinecall providers\` lists them): \`--realtime
xai/grok-voice-3.0 --realtime-option voice=eve\`; the --llm keeps answering the written calls, and
never names such a model. --greeting sets the words said as the call opens; \`--greeting
improvise\` has the model open on its prompt. --hangup any lets the model end the call whenever it
judges it done. --end-of-turn is who says the caller's turn is over. --remember and --forget
replace those lists whole. --llm-builds names a class of the vendor's plugin, and --llm-option
key=value one of its keyword arguments; --stt-…, --tts-… and --judge-… are the same for the ears,
the voice and the judge model. Those run only on your org's own key, as --realtime-option does.

A field the class declares itself (@voice, @llm, @realtime, @stt, a static field) says \`class\` in
every corner: the class wins, and a set or clear of it is refused naming the class.

knowledge is what the agent knows by heart, in Markdown, read whole on every call. Alone it
prints the corner's text; \`edit\` opens it in $EDITOR and saves what you wrote as the next
version (an empty file takes it out). It is not the RAG: the documents a turn searches are
\`pinecall docs\`, attached as \`bases\`.

clear takes fields out of the corner's own row, so the runtime's default stands for them again.
history, diff and rollback are the versions. pull prints the corner's config as JSON; push sends
a file as the next version. list prints every process holding this org's agents in the env;
stop <app> closes that app's socket.

Examples
  $ pinecall agent
  $ pinecall agent set --voice amelia --llm haiku --note "flat on the phone"
  $ pinecall agent list --prod
`;

const MELODY = `
The melody plays while a tool runs, and while the model has not said its first word, once the
agent has been quiet for the wait: a tool or a model that answers inside it plays nothing, and the
melody stops at the answer. It plays under the agent's voice at 60 %, looped, on the phone and on
the web alike, from the next call; a written call plays none.

default is the runtime's own melody, off is silence, upload sends a file of yours (the gateway
converts it once, to Ogg Opus). after sets the wait in seconds, 2.5 when you set none; choosing
what plays keeps the wait. One choice per agent per environment, whoever holds the agent:
--prod sets production's.

Examples
  $ pinecall pipeline melody
  $ pinecall pipeline melody upload espera.mp3
  $ pinecall pipeline melody after 1.5
  $ pinecall pipeline melody off --prod
`;

const LEXICON = `
The lexicon is the agent's says and hears, which the class never sets. add says how a word is
spoken; hear names the words the ears must know; rm takes words out of both. Whole and
versioned like the settings: the corner is yours (--team: the org's own).

Examples
  $ pinecall lexicon add DKV --say "de ka uve"
  $ pinecall lexicon hear "Vidal Ferrán"
  $ pinecall lexicon history
`;

const PIPELINE = `
The three legs of the pipeline as the NEXT call would be built — the vendor, the model and the
one knob worth showing — the opening, and the medians livekit measured over the agent's recent
calls. Setting them is \`pinecall agent set\`.
`;

const VOICES = `
The vendor is --tts, or Pinecall's own voice when none is named (\`pinecall providers\` says which).
With nothing after it: the vendor's voices in that language, one per line — the id the agent's
voice setting takes, the name, gender, and where the accent is from. --country keeps only the
voices from there.

play says the words in that voice, through the vendor's own plugin exactly as a call would, and
plays them here — afplay, ffplay, play, aplay or pw-play, whichever this machine has. With no
words, the gateway reads one line in the language. --save keeps the WAV where you say.

Examples
  $ pinecall voices --language es --country ES
  $ pinecall voices play de38f545-c574-44e8-9b54-a7d6fec1c6b1 "Hi, this is Clínica Norte's assistant." --language en
`;

export function register(program: Command, ctx: Context): void {
  const agent = program
    .command("agent")
    .description("what the org set over the class — yours, the team's, production's — setting it, and the processes that hold it")
    .addHelpText("after", AGENT);
  agent
    .command("show", { isDefault: true })
    .description("the settings in their three corners")
    .option("--agent <slug>")
    .action(async (flags) => ctx.io.result(await service.showSettings(ctx, flags.agent), render.settings));
  const set = agent.command("set").description("write the fields named as the next version of a corner").option("--agent <slug>").option("--team", "the org's own corner").option("--note <note>");
  for (const flag of ["voice", "tts", "tts-model", "stt", "llm", "llm-builds", "realtime", "stt-builds", "tts-builds", "judge", "judge-builds", "language", "greeting", "hangup"]) set.option(`--${flag} <value>`);
  for (const flag of ["temperature", "endpointing-ms", "min-interruption-words", "eot-threshold", "eager-eot-threshold", "max-duration"]) set.option(`--${flag} <n>`);
  for (const flag of ["greeting-interruptible", "record"]) set.option(`--${flag} <on|off>`);
  set.option("--end-of-turn <who>", END_OF_TURN_HELP);
  for (const stage of ["llm", "realtime", "stt", "tts", "judge"]) set.option(`--${stage}-option <key=value...>`);
  set.option("--remember <phrase...>").option("--forget <phrase...>");
  set.action(async (flags) => {
    const named = settingsOf(flags as Record<string, unknown>);
    if (Object.keys(named).length === 0) throw new UsageError("nothing to set: name a field (--voice, --llm, --greeting, …); `pinecall agent clear` takes one out");
    const input = service.SettingsInput.parse(named);
    ctx.io.result(await service.setSettings(ctx, input, service.WriteOptions.parse(flags)), render.settings);
  });
  agent
    .command("clear")
    .description("take fields out of the corner's own row, so the corner below holds again; --all takes every one")
    .argument("[fields...]", service.FIELDS.join(" · "))
    .option("--all", "every field of the corner's own row")
    .option("--agent <slug>")
    .option("--team")
    .action(async (fields, flags) => {
      // A whole corner gone is said in a word of its own, never by forgetting to name a field.
      if (fields.length === 0 && flags.all !== true) throw new UsageError("name the fields to clear, or --all for every one: `pinecall agent` shows what your corner sets");
      if (fields.length > 0 && flags.all === true) throw new UsageError("--all clears every field: name fields, or --all, not both");
      ctx.io.result(await service.clearSettings(ctx, fields, service.WriteOptions.parse(flags)), render.settings);
    });
  const knowledge = agent.command("knowledge").description("what the agent knows by heart: printed, or edited and kept as the next version");
  knowledge
    .command("show", { isDefault: true })
    .description("what the agent knows by heart, in its three corners")
    .option("--agent <slug>")
    .option("--team")
    .action(async (flags) => ctx.io.result(await service.readKnowledge(ctx, flags.agent, flags.team === true), render.knowledge));
  knowledge
    .command("edit")
    .description("the text in your editor; what you leave is the next version")
    .option("--agent <slug>")
    .option("--team")
    .option("--note <note>")
    .action(async (flags) => {
      const before = await service.readKnowledge(ctx, flags.agent, flags.team === true);
      const text = await editInEditor(before.knowledge ?? "", ctx.processEnv);
      if (text === (before.knowledge ?? "")) {
        ctx.io.print(render.UNCHANGED);
        return;
      }
      ctx.io.result(await service.writeKnowledge(ctx, text, service.WriteOptions.parse(flags)), (done) => render.knowledgeWritten(done, text));
    });
  agent
    .command("history")
    .description("every version of a corner, who set it and why")
    .option("--agent <slug>")
    .option("--team")
    .action(async (flags) => ctx.io.result(await service.settingsHistory(ctx, flags.agent, flags.team === true), render.history));
  agent
    .command("diff")
    .description("this corner against the team's or production's")
    .option("--agent <slug>")
    .option("--against <corner>", "team or production", "production")
    .option("--team", "the team's corner against production's, instead of yours")
    .action(async (flags) => {
      if (flags.against !== "team" && flags.against !== "production") throw new UsageError("--against takes team or production");
      if (flags.team === true && flags.against === "team") throw new UsageError("--team is the team's corner against production's: leave --against out, or say production");
      ctx.io.result(await service.settingsDiff(ctx, flags.agent, flags.against, flags.team === true), render.diff);
    });
  agent
    .command("rollback")
    .description("one version back as the next one")
    .argument("<version>")
    .option("--agent <slug>")
    .option("--team")
    .action(async (version, flags) => ctx.io.result(await service.rollbackSettings(ctx, Number(version), service.WriteOptions.parse(flags)), render.settings));
  agent
    .command("pull")
    .description("the corner's config as JSON")
    .option("--agent <slug>")
    .option("--team")
    .action(async (flags) => ctx.io.result(await service.pullSettings(ctx, flags.agent, flags.team === true), render.pulled));
  agent
    .command("push")
    .description("a file as the next version")
    .argument("<file>", "the file `pinecall agent pull` wrote")
    .option("--agent <slug>")
    .option("--team")
    .action(async (file, flags) => ctx.io.result(await service.pushSettings(ctx, file, service.WriteOptions.parse(flags)), render.pushed));
  agent
    .command("list")
    .description("every process holding this org's agents in the env")
    .action(async () => ctx.io.result(await service.listApps(ctx), render.apps));
  agent
    .command("stop")
    .description("close one app's socket; a pinecall that hears it exits instead of dialling back")
    .argument("<app>", "the first column of `pinecall agent list`")
    .action(async (app) => ctx.io.result(await service.stopApp(ctx, app), render.appStopped));
  program
    .command("kill")
    .description("an admin's: every app holding the agent in this env lets go of it and keeps its others; nothing is erased")
    .argument("[agent]", "the agent's slug; beside an agent's class, that agent")
    .action(async (agent) => ctx.io.result(await service.killAgent(ctx, agent), render.killed));

  const lexicon = program.command("lexicon").description("an agent's words: how the voice says them and what the ears must know").addHelpText("after", LEXICON);
  lexicon
    .command("show", { isDefault: true })
    .description("the words and how they are said and heard, in the three corners")
    .option("--agent <slug>")
    .action(async (flags) => ctx.io.result(await service.showLexicon(ctx, flags.agent), render.lexicon));
  lexicon
    .command("add")
    .description("how a word is spoken")
    .argument("<word>")
    .requiredOption("--say <spoken>")
    .option("--agent <slug>")
    .option("--team")
    .option("--note <note>")
    .action(async (word, flags) => ctx.io.result(await service.sayWord(ctx, service.SayWordInput.parse({ word, ...flags })), render.lexicon));
  lexicon
    .command("hear")
    .description("the words the ears must know")
    .argument("<words...>")
    .option("--agent <slug>")
    .option("--team")
    .option("--note <note>")
    .action(async (words, flags) => ctx.io.result(await service.hearWords(ctx, service.WordsInput.parse({ words, ...flags })), render.lexicon));
  lexicon
    .command("rm")
    .description("words taken out of both")
    .argument("<words...>")
    .option("--agent <slug>")
    .option("--team")
    .action(async (words, flags) => ctx.io.result(await service.removeWords(ctx, service.WordsInput.parse({ words, ...flags })), render.lexicon));
  lexicon
    .command("history")
    .description("every version of a corner's lexicon, who set it and why")
    .option("--agent <slug>")
    .option("--team")
    .action(async (flags) => ctx.io.result(await service.lexiconHistory(ctx, flags.agent, flags.team === true), render.lexiconHistory));

  const pipeline = program
    .command("pipeline")
    .description("what the agent hears, decides and speaks with, as the next call would be built")
    .option("--agent <slug>")
    .addHelpText("after", PIPELINE)
    .action(async (flags) => ctx.io.result(await service.showPipeline(ctx, flags.agent), render.pipeline));
  const melody = pipeline.command("melody").description("what a caller hears while a tool runs or the model is slow, and after how long").addHelpText("after", MELODY);
  melody
    .command("show", { isDefault: true })
    .description("what plays and after how many seconds of quiet")
    .option("--agent <slug>")
    .action(async (flags) => ctx.io.result(await service.showMelody(ctx, flags.agent), render.melody));
  melody
    .command("upload")
    .description("a file of yours as the melody, from the next call")
    .argument("<file>", "a wav, an mp3, an ogg, a flac or an m4a, up to 20 MB and five minutes")
    .option("--agent <slug>")
    .action(async (file, flags) => ctx.io.result(await service.uploadMelody(ctx, flags.agent, file), render.melody));
  for (const [played, said] of [["default", "the runtime's own melody back"], ["off", "nothing plays: the caller hears silence"]] as const) {
    melody
      .command(played)
      .description(said)
      .option("--agent <slug>")
      .action(async (flags) => ctx.io.result(await service.chooseMelody(ctx, flags.agent, played), render.melody));
  }
  melody
    .command("after")
    .description("seconds of the agent's quiet before the melody starts")
    .argument("<seconds>", "0 to 30, or default for the runtime's own")
    .option("--agent <slug>")
    .action(async (seconds, flags) => ctx.io.result(await service.waitBeforeMelody(ctx, flags.agent, service.AfterInput.parse(seconds)), render.melody));
  // The six knobs moved into the settings: the old verbs name where, instead of "too many arguments".
  for (const moved of ["set", "clear"]) pipeline.command(moved, { hidden: true }).allowUnknownOption().allowExcessArguments().action(() => { throw new UsageError(`pipeline ${moved} is \`pinecall agent ${moved}\` now: the stages are fields of the settings`); });

  const voices = program.command("voices").description("a voice vendor's voices, and any one of them heard on this machine before it is chosen").addHelpText("after", VOICES);
  voices
    .command("list", { isDefault: true })
    .description("a vendor's voices, by language and country")
    .option("--tts <vendor>")
    .option("--language <tag>")
    .option("--country <XX>")
    .action(async (flags) => ctx.io.result(await service.listVoices(ctx, service.ListVoicesInput.parse(flags)), render.voices));
  voices
    .command("play")
    .description("the words said in that voice, played here")
    .argument("<voice>", "the voice's id")
    .argument("[words]", "what to say; the gateway's own line in the language when left out")
    .option("--tts <vendor>")
    .option("--model <model>")
    .option("--language <tag>")
    .option("--save <file.wav>", "keep the WAV")
    .action(async (voice, words, flags) => {
      const input = service.SampleVoiceInput.parse({ voice, text: words, tts: flags.tts, model: flags.model, language: flags.language });
      ctx.io.result(await service.playVoice(ctx, input, flags.save, playFile), render.voicePlayed);
    });
}

const END_OF_TURN_HELP = "who says the caller's turn is over: stt (the ears themselves), livekit or smart-turn";

// The flags as typed, under the CLI's own names, numbers read as numbers and options as pairs.
function settingsOf(flags: Record<string, unknown>): Record<string, unknown> {
  const named: Record<string, unknown> = {};
  const text = (flag: string): string | undefined => flags[camel(flag)] as string | undefined;
  for (const flag of ["voice", "tts", "tts-model", "stt", "llm", "llm-builds", "realtime", "stt-builds", "tts-builds", "judge", "judge-builds", "language", "greeting", "hangup", "greeting-interruptible", "record", "end-of-turn"]) {
    if (text(flag) !== undefined) named[flag] = text(flag);
  }
  for (const flag of ["temperature", "endpointing-ms", "min-interruption-words", "eot-threshold", "eager-eot-threshold"]) {
    const value = numberOf(`--${flag}`, text(flag));
    if (value !== undefined) named[flag] = value;
  }
  const limit = text("max-duration");
  if (limit !== undefined) named["max-duration"] = limit === "off" ? "off" : Number(limit);
  for (const stage of ["llm", "realtime", "stt", "tts", "judge"]) {
    const options = parseKeyValues(`${stage}-option`, flags[`${stage}Option`] as string[] | undefined);
    if (options !== undefined) named[`${stage}-options`] = options;
  }
  if (flags["remember"] !== undefined) named["remember"] = flags["remember"];
  if (flags["forget"] !== undefined) named["forget"] = flags["forget"];
  return named;
}

function camel(flag: string): string {
  return flag.replace(/-([a-z])/g, (_dash, letter: string) => letter.toUpperCase());
}
