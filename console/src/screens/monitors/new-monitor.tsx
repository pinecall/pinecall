/** The form a monitor is written in: a name, the number watched, the line and its side, the window, and whose agent. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Field, Input, Segmented, Select, SelectItem, TextAction } from "../../ui";
import { addMonitor, type Monitor, type MonitorMetric, type MonitorPut } from "./door";
import { METRIC_WORDS, METRICS } from "./metrics";

type Window = MonitorPut["window_days"];
const WINDOWS: readonly { value: `${Window}`; label: string }[] = [
  { value: "1", label: "24 h" },
  { value: "7", label: "7 d" },
  { value: "30", label: "30 d" },
];

/** With one agent in view the monitor is that agent's; with every agent in view it is the world's, or one agent's by name. */
export function NewMonitor({ agent, onSaved, onClose }: { agent: string; onSaved: (kept: Monitor) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState("");
  const [metric, setMetric] = useState<MonitorMetric>("e2e_median_s");
  const [above, setAbove] = useState<"above" | "below">("above");
  const [threshold, setThreshold] = useState("");
  const [days, setDays] = useState<`${Window}`>("7");
  const [whose, setWhose] = useState("");
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const words = METRIC_WORDS[metric];
  const line = Number(threshold);
  const ready = name.trim() !== "" && threshold.trim() !== "" && Number.isFinite(line) && !saving;

  const pick = (next: string): void => {
    const chosen = next as MonitorMetric;
    setMetric(chosen);
    setAbove(METRIC_WORDS[chosen].above ? "above" : "below");
  };

  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      const named = agent === "" ? whose.trim() : agent;
      onSaved(await addMonitor(credentials, { name: name.trim(), metric, above: above === "above", threshold: line, window_days: Number(days) as Window, agent: named === "" ? null : named }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="mon-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) void save();
      }}
    >
      <div className="ui-form">
        <Field label="Name, as the alert will read" grow minWidth={220}>
          <Input value={name} placeholder="slow answers" autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Watches" minWidth={260}>
          <Select value={metric} onValueChange={pick} aria-label="the number watched">
            {METRICS.map((one) => (
              <SelectItem key={one} value={one}>
                {METRIC_WORDS[one].name}
              </SelectItem>
            ))}
          </Select>
        </Field>
      </div>
      <p className="mon-hint">{words.means}; read over the window, for {agent === "" ? "every agent's calls or one agent's" : `${agent}'s calls`}.</p>
      <div className="ui-form">
        <Field label="Fires when it is">
          <Segmented
            options={[
              { value: "above", label: "above" },
              { value: "below", label: "below" },
            ]}
            value={above}
            onChange={setAbove}
          />
        </Field>
        <Field label={`The line${metric.endsWith("_rate") ? ", 0 to 1" : metric.endsWith("_s") ? ", seconds" : metric === "spend_usd" ? ", dollars" : ""}`} minWidth={140}>
          <Input value={threshold} inputMode="decimal" placeholder={metric.endsWith("_rate") ? "0.9" : "2"} onChange={(event) => setThreshold(event.target.value)} />
        </Field>
        <Field label="Over">
          <Segmented options={WINDOWS} value={days} onChange={setDays} />
        </Field>
        {agent === "" && (
          <Field label="Agent" minWidth={160}>
            <Input value={whose} placeholder="every agent" autoComplete="off" spellCheck={false} onChange={(event) => setWhose(event.target.value)} />
          </Field>
        )}
      </div>
      <div className="mon-form-foot">
        <Button kind="primary" size="form" type="submit" disabled={!ready}>
          {saving ? "Saving…" : "Watch it"}
        </Button>
        <TextAction onClick={onClose}>Cancel</TextAction>
        {refused !== null && <span className="mon-bad">{refused}</span>}
      </div>
    </form>
  );
}
