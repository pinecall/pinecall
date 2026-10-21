/** The Pipeline tab: the three stages of a turn and the judge as four tiles saying what each runs, the one picked opening its settings below, and the switch that gives voice calls a realtime model of their own. */

import { useState, type ReactNode } from "react";

import type { Provider } from "../../lib/catalogue";
import { Icon, Switch, type IconName } from "../../ui";
import { LanguageField } from "./language";
import { EndOfTurnField, FixedByTheClass, PluginFields, TemperatureField } from "./plugin";
import { RealtimeSection } from "./realtime";
import { StageSection, VoiceField } from "./stages";
import { wordOf, type Change, type Knob, type Modeled, type Plugin, type Typed } from "./typed";

/** Which stage's settings are open below the tiles. */
export type Step = "hears" | "decides" | "speaks" | "judged";

const TILES: readonly { step: Step; name: string; icon: IconName; modality: "stt" | "llm" | "tts" }[] = [
  { step: "hears", name: "Hears", icon: "ear", modality: "stt" },
  { step: "decides", name: "Thinks", icon: "memory", modality: "llm" },
  { step: "speaks", name: "Speaks", icon: "speaker", modality: "tts" },
  { step: "judged", name: "Judged by", icon: "scale", modality: "llm" },
];

/** What the agent's class declares at each stage, as the next call runs it; null while asked for. */
export interface Running {
  hears: string | null;
  decides: string | null;
  speaks: string | null;
  talks: string | null;
  language: string | null;
}

export interface PipelineProps {
  typed: Typed;
  change: Change;
  knob: (field: "stt" | "llm" | "tts" | "judge" | "realtime") => (picked: Knob) => void;
  plug: (modality: Modeled) => (plugin: Plugin) => void;
  providers: readonly Provider[];
  defaults: Readonly<Record<string, string>>;
  models: Readonly<Record<string, readonly string[]>>;
  /** By "<modality>/<vendor>", the model a call runs when none is picked, where the runtime knows it. */
  runsOn: Readonly<Record<string, string>>;
  realtime: Readonly<Record<string, readonly string[]>>;
  fixed: ReadonlySet<string>;
  running: Running | null;
  /** The agent's language for listing voices; null when undeclared. */
  language: string | null;
  own: ReadonlySet<string>;
  step: Step;
  onStep: (step: Step) => void;
}

// The wire word a stage runs: what is picked, else the runtime's default vendor and the model that runs on it when none is picked.
function runs(picked: Knob, modality: "stt" | "llm" | "tts", defaults: PipelineProps["defaults"], runsOn: PipelineProps["runsOn"]): string {
  if (picked.vendor !== "" && picked.model !== "") return wordOf(picked);
  const vendor = picked.vendor === "" ? (defaults[modality] ?? "") : picked.vendor;
  const model = picked.model === "" ? runsOn[`${modality}/${vendor}`] : picked.model;
  return model === undefined ? vendor : `${vendor}/${model}`;
}

export function Pipeline(props: PipelineProps): ReactNode {
  const { typed, change, knob, plug, providers, defaults, models, runsOn, realtime, fixed, running, language, own, step, onStep } = props;
  const [realtimeOn, setRealtimeOn] = useState(typed.realtime.vendor !== "");
  const speaking = typed.tts.vendor === "" ? (defaults["tts"] ?? null) : typed.tts.vendor;
  const vendorOf = (picked: string, fallback: string | undefined): string => (picked === "" ? (fallback ?? "the vendor") : picked);

  const said = (at: Step): { value: string; under: string } => {
    const tile = TILES.find((one) => one.step === at);
    if (tile === undefined) return { value: "", under: "" };
    const classes: Record<Step, string | null | undefined> = { hears: fixed.has("stt") ? running?.hears : undefined, decides: fixed.has("llm") ? running?.decides : undefined, speaks: fixed.has("voice") ? running?.speaks : undefined, judged: fixed.has("judge") ? "" : undefined };
    const fromClass = classes[at];
    const picked = at === "hears" ? typed.stt : at === "decides" ? typed.llm : at === "speaks" ? typed.tts : typed.judge;
    const value = fromClass !== undefined ? (fromClass === null || fromClass === "" ? "set by the class" : fromClass) : at === "judged" && picked.vendor === "" ? "the org's choice" : runs(picked, tile.modality, defaults, runsOn);
    const under = { hears: typed.language === "" ? "language not set" : `language ${typed.language}`, decides: typed.temperature === "" ? "default temperature" : `temperature ${typed.temperature}`, speaks: typed.voice === "" ? "the model's own voice" : `as ${typed.voice}`, judged: "at hang-up" }[at];
    return { value, under };
  };

  return (
    <div className="set-pipeline">
      <div className="set-tiles" role="tablist" aria-label="Stages of a turn">
        {TILES.map((tile) => {
          const at = said(tile.step);
          return (
            <button key={tile.step} type="button" role="tab" aria-selected={step === tile.step} className={step === tile.step ? "set-tile set-tile-on" : "set-tile"} onClick={() => onStep(tile.step)}>
              <span className="set-tile-name">
                <Icon name={tile.icon} size={15} />
                {tile.name}
              </span>
              <span className="set-tile-value">{at.value}</span>
              <span className="set-tile-under">{at.under}</span>
            </button>
          );
        })}
      </div>

      <div className="set-realtime">
        <span className="set-realtime-icon" aria-hidden>
          <Icon name="zap" size={18} />
        </span>
        <span className="set-realtime-words">
          <span className="set-realtime-title">Run voice calls on a realtime model</span>
          <span className="set-realtime-under">
            {fixed.has("realtime")
              ? `Set by the class${running?.talks == null ? "" : `: ${running.talks}`}.`
              : realtimeOn
                ? typed.realtime.vendor === ""
                  ? "On. Pick the model below."
                  : `On. Voice calls run on ${wordOf(typed.realtime)} alone.`
                : "Off. Voice calls use the three stages above."}
          </span>
        </span>
        {!fixed.has("realtime") && (
          <Switch
            on={realtimeOn}
            label="Run voice calls on a realtime model"
            onChange={(on) => {
              setRealtimeOn(on);
              // Off runs the calls on the three stages again: what was picked goes with it, its options too.
              if (!on) knob("realtime")({ vendor: "", model: "" });
            }}
          />
        )}
      </div>
      {(realtimeOn || fixed.has("realtime")) && (
        <RealtimeSection
          knob={typed.realtime}
          options={typed.realtime_options}
          providers={providers}
          realtime={realtime}
          fixed={fixed.has("realtime") ? { value: running?.talks ?? null } : undefined}
          onChange={knob("realtime")}
          onOptions={(options) => change("realtime_options", options)}
        />
      )}

      {step === "hears" && (
        <StageSection
          modality="stt"
          title="Hears"
          blurb="What turns the caller's voice into words, and in which language."
          knob={typed.stt}
          providers={providers}
          defaults={defaults}
          models={models}
          runs={runsOn}
          own={own}
          onChange={knob("stt")}
          fixed={fixed.has("stt") ? { value: running?.hears ?? null } : undefined}
          advanced={!fixed.has("stt") && (
            <>
              <EndOfTurnField endOfTurn={typed.end_of_turn} onChange={(picked) => change("end_of_turn", picked)} />
              <PluginFields modality="stt" vendor={vendorOf(typed.stt.vendor, defaults["stt"])} plugin={typed.plugins.stt} onChange={plug("stt")} />
            </>
          )}
        >
          {fixed.has("language") ? <FixedByTheClass label="Language" value={running?.language} /> : <LanguageField language={typed.language} onChange={(picked) => change("language", picked)} />}
        </StageSection>
      )}
      {step === "decides" && (
        <StageSection
          modality="llm"
          title="Thinks"
          blurb="The model that reads what the caller said and writes the answer."
          knob={typed.llm}
          providers={providers}
          defaults={defaults}
          models={models}
          runs={runsOn}
          own={own}
          onChange={knob("llm")}
          fixed={fixed.has("llm") ? { value: running?.decides ?? null } : undefined}
          advanced={!fixed.has("llm") && <PluginFields modality="llm" vendor={vendorOf(typed.llm.vendor, defaults["llm"])} plugin={typed.plugins.llm} onChange={plug("llm")} />}
        >
          {!fixed.has("llm") && <TemperatureField temperature={typed.temperature} onChange={(picked) => change("temperature", picked)} />}
        </StageSection>
      )}
      {step === "speaks" && (
        <StageSection
          modality="tts"
          title="Voice"
          blurb="Says the answer out loud."
          knob={typed.tts}
          providers={providers}
          defaults={defaults}
          models={models}
          runs={runsOn}
          own={own}
          onChange={knob("tts")}
          fixed={fixed.has("voice") ? { value: running?.speaks ?? null } : undefined}
          advanced={!fixed.has("voice") && <PluginFields modality="tts" vendor={vendorOf(typed.tts.vendor, defaults["tts"])} plugin={typed.plugins.tts} onChange={plug("tts")} />}
        >
          {!fixed.has("voice") && <VoiceField vendor={speaking} providers={providers} model={typed.tts.model === "" ? null : typed.tts.model} language={language} opening={typed.say} voice={typed.voice} onChange={(picked) => change("voice", picked)} />}
        </StageSection>
      )}
      {step === "judged" && (
        <StageSection
          modality="llm"
          title="Judge"
          blurb="The model this agent's calls are judged on at hang-up. Unset, the org's choice in Quality ▸ Judges, else Pinecall's. On your org's own key — a model on your own server among them, through base_url — its evals are not billed."
          knob={typed.judge}
          providers={providers}
          defaults={defaults}
          models={models}
          runs={runsOn}
          own={own}
          onChange={knob("judge")}
          unset="The org's choice, else Pinecall's"
          fixed={fixed.has("judge") ? { value: null } : undefined}
          advanced={!fixed.has("judge") && typed.judge.vendor !== "" && <PluginFields modality="judge" vendor={typed.judge.vendor} plugin={typed.plugins.judge} onChange={plug("judge")} />}
        />
      )}
    </div>
  );
}
