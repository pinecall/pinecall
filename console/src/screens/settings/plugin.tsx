/** A stage's plugin class and options, the model's temperature, and a field the agent's class fixes. */

import type { ReactNode } from "react";

import { Input, Label, Select, SelectItem, TextArea } from "../../ui";
import type { Modeled, Plugin, Typed } from "./typed";

const EXAMPLES: Readonly<Record<Modeled, { builds: string; options: string }>> = {
  llm: { builds: "responses.LLM", options: '{ "use_websocket": true }' },
  stt: { builds: "STTv2", options: '{ "eot_timeout_ms": 900 }' },
  tts: { builds: "", options: '{ "speed": 1.1 }' },
  judge: { builds: "", options: '{ "base_url": "http://your-gpu:8000/v1" }' },
};

export function TemperatureField({ temperature, onChange }: { temperature: string; onChange: (temperature: string) => void }): ReactNode {
  return (
    <div className="set-row">
      <div className="set-field">
        <Label>Temperature</Label>
        <Input value={temperature} inputMode="decimal" aria-label="Temperature" placeholder="The vendor's default" onChange={(event) => onChange(event.target.value)} />
        <p className="set-help">How freely the model picks its words, in its vendor&apos;s own range. Lower answers the same way every time.</p>
      </div>
    </div>
  );
}

/** The plugin's class and its keyword arguments, for a vendor whose plugin takes more than the form asks. */
export function PluginFields({ modality, vendor, plugin, onChange }: { modality: Modeled; vendor: string; plugin: Plugin; onChange: (plugin: Plugin) => void }): ReactNode {
  const example = EXAMPLES[modality];
  return (
    <div className="set-row">
      <div className="set-field">
        <Label>Plugin class</Label>
        <Input value={plugin.builds} aria-label="Plugin class" spellCheck={false} placeholder={example.builds === "" ? "The plugin's default" : example.builds} onChange={(event) => onChange({ ...plugin, builds: event.target.value })} />
        <p className="set-help">A class of {vendor}&apos;s LiveKit plugin other than its default; a dot reaches into a module of it.</p>
      </div>
      <div className="set-field">
        <Label>Plugin options</Label>
        <TextArea value={plugin.options} rows={3} aria-label="Plugin options" spellCheck={false} placeholder={example.options} onChange={(event) => onChange({ ...plugin, options: event.target.value })} />
        <p className="set-help">Its keyword arguments as JSON, named as the plugin names them. Both run only on your org&apos;s own {vendor} key, never on one Pinecall lends.</p>
      </div>
    </div>
  );
}

const ENDINGS: readonly { value: Typed["end_of_turn"]; label: string }[] = [
  { value: "", label: "The box's choice for these ears" },
  { value: "stt", label: "The ears themselves · Deepgram Flux" },
  { value: "smart-turn", label: "Smart Turn v3, read off the audio" },
  { value: "livekit", label: "LiveKit's detector, read off the audio" },
];

/** Who says the caller's turn is over. */
export function EndOfTurnField({ endOfTurn, onChange }: { endOfTurn: Typed["end_of_turn"]; onChange: (endOfTurn: Typed["end_of_turn"]) => void }): ReactNode {
  return (
    <div className="set-row">
      <div className="set-field">
        <Label>End of turn</Label>
        <Select value={endOfTurn} aria-label="End of turn" onValueChange={(value) => onChange(value as Typed["end_of_turn"])}>
          {ENDINGS.map((one) => (
            <SelectItem key={one.value} value={one.value}>
              {one.label}
            </SelectItem>
          ))}
        </Select>
        <p className="set-help">Who says the caller has finished. The ears end it only where they can (Flux); Smart Turn and LiveKit&apos;s detector run beside any ears, on any key.</p>
      </div>
    </div>
  );
}

/** A setting the agent's class declares: shown, never edited here. */
export function FixedByTheClass({ label, value }: { label: string; value?: string | null | undefined }): ReactNode {
  return (
    <div className="set-field set-wide">
      <Label>{label}</Label>
      <p className="set-help">
        {value === undefined || value === null || value === "" ? "Set by the class." : <>Set by the class: <code>{value}</code>.</>} The class&apos;s declaration wins over these settings: change it in
        the code, or take it out of the class to set it here.
      </p>
    </div>
  );
}
