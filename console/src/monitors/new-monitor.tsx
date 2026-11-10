/** A monitor written, in the side panel: its name, the number watched, the line and its side, the window, and whose calls. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { EditDialog } from "../configure/dialog";
import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { addMonitor, type Monitor, type MonitorMetric, type MonitorPut } from "./door";
import { METRICS, ruleOf } from "./words";

type Window = MonitorPut["window_days"];
const WINDOWS: readonly { value: Window; name: string }[] = [
  { value: 1, name: "A day" },
  { value: 7, name: "7 days" },
  { value: 30, name: "30 days" },
];
const EVERY_AGENT = "";

/** `agent` writes it for that agent alone, with no choice shown; without one, the person picks an agent or every agent. */
export function NewMonitorPanel({ agent, agents, onSaved, onClose }: { agent: string | null; agents: readonly string[]; onSaved: (kept: Monitor) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState("");
  const [metric, setMetric] = useState<MonitorMetric>("e2e_median_s");
  const [above, setAbove] = useState(true);
  const [line, setLine] = useState("");
  const [days, setDays] = useState<Window>(7);
  const [whose, setWhose] = useState(EVERY_AGENT);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const words = METRICS[metric];
  const typed = Number(line.replace(",", "."));
  const valid = line.trim() !== "" && Number.isFinite(typed);
  // A share is typed as a percentage and kept as the gateway keeps it, 0 to 1.
  const threshold = words.share ? typed / 100 : typed;
  const scope = agent ?? (whose === EVERY_AGENT ? null : whose);

  const pick = (next: string): void => {
    const chosen = next as MonitorMetric;
    setMetric(chosen);
    setAbove(METRICS[chosen].above);
    setLine("");
  };

  const save = async (): Promise<void> => {
    if (name.trim() === "") return setRefused("Name it: the alert reads with this name.");
    if (!valid) return setRefused(`Type the line as a number of ${words.unit}.`);
    if (words.share && (typed < 0 || typed > 100)) return setRefused("A share goes from 0 to 100.");
    setSaving(true);
    setRefused(null);
    try {
      onSaved(await addMonitor(credentials, { name: name.trim(), metric, above, threshold, window_days: days, agent: scope }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EditDialog title="New monitor" icon="monitors" about="A number of the calls, watched over a window. When it crosses the line it fires once a day: an alert is kept, the org's admins are mailed, and the webhook is posted." saving={saving} refused={refused} onSave={() => void save()} onClose={onClose}>
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="Slow answers" autoFocus value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field label="Watches">
        <Select label="Watches" searchable={false} items={(Object.keys(METRICS) as MonitorMetric[]).map((one) => ({ value: one, label: METRICS[one].name, detail: METRICS[one].means }))} value={metric} onChange={pick} />
      </Field>
      <Field label="Fires when it is">
        <div className="mon-line">
          <div className="dash-switch" role="group" aria-label="The side that fires">
            <button type="button" aria-pressed={above} className={above ? "dash-switch-on" : ""} onClick={() => setAbove(true)}>
              Above
            </button>
            <button type="button" aria-pressed={!above} className={above ? "" : "dash-switch-on"} onClick={() => setAbove(false)}>
              Below
            </button>
          </div>
          <input className="cfg-input" aria-label={`The line, in ${words.unit}`} inputMode="decimal" placeholder={words.example} value={line} onChange={(event) => setLine(event.target.value)} />
          <span className="mon-unit">{words.unit}</span>
        </div>
      </Field>
      <Field label="Over the last">
        <div className="dash-switch mon-windows" role="group" aria-label="Over the last">
          {WINDOWS.map((one) => (
            <button key={one.value} type="button" aria-pressed={days === one.value} className={days === one.value ? "dash-switch-on" : ""} onClick={() => setDays(one.value)}>
              {one.name}
            </button>
          ))}
        </div>
      </Field>
      {agent === null && (
        <Field label="Whose calls">
          <Select label="Whose calls" items={[{ value: EVERY_AGENT, label: "Every agent", detail: "The whole organization's calls together" }, ...agents.map((one) => ({ value: one, label: one }))]} value={whose} onChange={setWhose} />
        </Field>
      )}
      {valid && (
        <p className="mon-reads">
          Fires when <b>{ruleOf({ metric, above, threshold, window_days: days }).replace(/^./, (first) => first.toLowerCase())}</b>, for {scope === null ? "every agent's calls" : `${scope}'s calls`}.
        </p>
      )}
    </EditDialog>
  );
}
