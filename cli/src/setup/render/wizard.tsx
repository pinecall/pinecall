/** The setup screen: the machine read, a way chosen, each stage picked where asked, the keys' whereabouts, the answers confirmed. */

import { Box, Text, render, useApp, useInput } from "ink";
import { useState } from "react";

import { LOCAL, type Answers, type Option, type Read, type Stage, type Vendor, answersFrom, optionsFor, turnOf, whereKeyIs } from "../service.js";
import { Choose } from "./choose.js";
import { MachinePanel } from "./machine.js";
import { Pick } from "./pick.js";

/** What the wizard needs beside the terminal: the machine as read, the build's vendors, where the keys are. */
export interface WizardInput {
  read: Read;
  vendors: Vendor[];
  env: NodeJS.ProcessEnv;
  keysInFiles: Record<string, string>;
  /** The stages a flag named already: shown, not asked. */
  flags: Partial<Answers>;
}

type Way = "recommended" | "local" | "keys" | "mix" | "chat";
type Step = { at: "way" } | { at: "stage"; stage: Stage } | { at: "confirm" };

const ASKED: Stage[] = ["stt", "turn", "llm", "tts", "judge", "caller"];
const ABOUT: Record<Stage, [string, string]> = {
  stt: ["ears", "who hears the caller"],
  turn: ["end of turn", "who decides the caller stopped talking"],
  llm: ["thinking", "which model answers; local/<tag> runs any model Ollama has"],
  tts: ["voice", "who speaks"],
  judge: ["judge", "which model judges a finished call"],
  caller: ["caller", "which model plays the simulated caller"],
};

/** The wizard on the terminal; the answers, or undefined when the person left it. */
export function wizard(input: WizardInput, terminal: { stdout: NodeJS.WriteStream; stdin: NodeJS.ReadStream }): Promise<Answers | undefined> {
  return new Promise((resolve) => {
    const app = render(<Wizard input={input} onDone={(answers) => { resolve(answers); app.unmount(); }} />, {
      stdout: terminal.stdout,
      stdin: terminal.stdin,
      exitOnCtrlC: true,
    });
    void app.waitUntilExit().then(() => resolve(undefined));
  });
}

function Wizard({ input, onDone }: { input: WizardInput; onDone: (answers: Answers | undefined) => void }): React.JSX.Element {
  const { exit } = useApp();
  const recommended = answersFrom(input.read, input.flags);
  const [answers, setAnswers] = useState<Answers>(recommended);
  const [step, setStep] = useState<Step>({ at: "way" });
  const [way, setWay] = useState<Way>("recommended");
  useInput((input_, key) => {
    if (key.ctrl && input_ === "c") exit();
  });
  const leave = (): void => { onDone(undefined); exit(); };
  const toAsk = (from: Way): Stage[] => (from === "mix" ? ASKED.filter((stage) => input.flags[stage] === undefined) : []);
  const next = (chosen: Way, done: Stage): void => {
    const left = toAsk(chosen);
    const following = left[left.indexOf(done) + 1];
    setStep(following === undefined ? { at: "confirm" } : { at: "stage", stage: following });
  };
  const chooseWay = (value: string): void => {
    const chosen = value as Way;
    setWay(chosen);
    const keys = input.read.recommendation.keys;
    const all = (stage: string): string => keys[stage]?.vendor ?? LOCAL;
    if (chosen === "recommended") setAnswers(recommended);
    if (chosen === "local") setAnswers({ ...recommended, stt: LOCAL, turn: "smart-turn", llm: localThinking(input.read), tts: LOCAL, judge: localThinking(input.read), caller: localThinking(input.read), chatOnly: false });
    if (chosen === "keys") setAnswers({ ...recommended, stt: all("stt"), turn: "stt", llm: all("llm"), tts: all("tts"), judge: all("llm"), caller: all("llm"), chatOnly: false });
    if (chosen === "chat") setAnswers({ ...recommended, stt: LOCAL, turn: "smart-turn", tts: LOCAL, chatOnly: true });
    const first = toAsk(chosen)[0];
    setStep(first === undefined ? { at: "confirm" } : { at: "stage", stage: first });
  };
  const pick = (stage: Stage, value: string): void => {
    setAnswers((before) => {
      const after = { ...before, [stage]: stage === "turn" ? turnOf(value) : value };
      // The judge and the caller follow the thinking until picked on their own.
      if (stage === "llm") return { ...after, judge: before.judge === before.llm ? value : before.judge, caller: before.caller === before.llm ? value : before.caller };
      return after;
    });
    next(way, stage);
  };
  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold color="green">{"pinecall setup"}</Text>
      <Text dimColor>{"the runtime on this machine: Postgres, Redis and LiveKit in Docker, the schema, a key this CLI finds by itself, the models"}</Text>
      <Box marginTop={1} flexDirection="column">
        <MachinePanel read={input.read} />
      </Box>
      <Box marginTop={1} flexDirection="column">
        {step.at === "way" && <Choose title="how?" choices={ways(input.read)} initial="recommended" onChoose={chooseWay} />}
        {step.at === "stage" && (
          <Pick
            key={step.stage}
            title={`${ABOUT[step.stage][0]}: ${answers[step.stage]}`}
            about={ABOUT[step.stage][1]}
            options={options(step.stage, input, answers)}
            initial=""
            freeText={step.stage === "llm" || step.stage === "judge" || step.stage === "caller"}
            onPick={(value) => pick(step.stage, value)}
            onBack={() => setStep({ at: "way" })}
          />
        )}
        {step.at === "confirm" && (
          <Confirm answers={answers} input={input} onYes={() => { onDone(answers); exit(); }} onBack={() => setStep({ at: "way" })} onLeave={leave} />
        )}
      </Box>
    </Box>
  );
}

function Confirm({ answers, input, onYes, onBack, onLeave }: { answers: Answers; input: WizardInput; onYes: () => void; onBack: () => void; onLeave: () => void }): React.JSX.Element {
  useInput((typed, key) => {
    if (key.return || typed === "y") onYes();
    if (key.escape) onBack();
    if (typed === "q") onLeave();
  });
  const vendors = new Set([answers.stt, answers.llm, answers.tts, answers.judge, answers.caller].filter((one) => !one.startsWith(LOCAL)).map((one) => one.split("/")[0]!));
  return (
    <Box flexDirection="column">
      <Text bold>{"this is what runs"}</Text>
      {ASKED.map((stage) => (
        <Box key={stage}>
          <Text>{`  ${ABOUT[stage][0].padEnd(12)}`}</Text>
          <Text color="cyan">{answers[stage]}</Text>
        </Box>
      ))}
      {answers.chatOnly && <Text>{"  written calls alone: no LiveKit, no worker"}</Text>}
      {[...vendors].map((vendor) => {
        const variable = `${vendor.toUpperCase().replace(/-/g, "_")}_API_KEY`;
        return (
          <Box key={vendor}>
            <Text>{`  ${variable.padEnd(24)}`}</Text>
            <Text dimColor>{whereKeyIs(variable, input.env, input.keysInFiles)}</Text>
          </Box>
        );
      })}
      <Box marginTop={1}>
        <Text dimColor>{"⏎ run pinecall-runtime setup with these · esc back · q leave"}</Text>
      </Box>
    </Box>
  );
}

function ways(read: Read): { value: Way; label: string; hint: string }[] {
  const stack = read.recommendation.stack;
  return [
    { value: "recommended", label: "recommended", hint: `${stack["stt"]} · ${stack["turn"]} · ${stack["llm"]} · ${stack["tts"]} — what this machine runs best` },
    { value: "local", label: "all local", hint: "every stage an open model on this machine, no account anywhere" },
    { value: "keys", label: "with keys", hint: "deepgram hears, anthropic thinks, cartesia speaks: the vendors Cloud runs on" },
    { value: "mix", label: "stage by stage", hint: "pick the ears, the end of turn, the thinking, the voice, the judge and the caller" },
    { value: "chat", label: "chat only", hint: "written calls alone: no LiveKit, no worker, no ears, no voice" },
  ];
}

function localThinking(read: Read): string {
  const fits = read.recommendation.candidates.find((one) => one.fits);
  return fits === undefined ? LOCAL : `${LOCAL}/${fits.model}`;
}

function options(stage: Stage, input: WizardInput, answers: Answers): Option[] {
  return optionsFor(stage, input.read, input.vendors, answers.stt.split("/")[0]);
}
