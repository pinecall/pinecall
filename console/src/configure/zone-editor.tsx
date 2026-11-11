/** The agent's time zone, picked from a list that is searched: the clock its calls open on. */

import { useMemo, useState, type ReactNode } from "react";

import { Select, type SelectItem } from "../ui/select";
import { Field } from "../ui/setting";
import { EditDialog } from "./dialog";

// Every IANA zone the browser knows; one it does not list (set from the CLI) is listed beside them as it is kept.
const ZONES: readonly string[] = Intl.supportedValuesOf("timeZone");
const HERE = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** A zone's offset and the hour it is there now ("GMT-3 · 14:32"), or null for a name that is no zone. */
function clockIn(zone: string, now: Date): string | null {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" }).formatToParts(now);
    const part = (type: string): string => parts.find((one) => one.type === type)?.value ?? "";
    return `${part("timeZoneName")} · ${part("hour")}:${part("minute")}`;
  } catch {
    return null;
  }
}

/** One zone as a row: its name, its offset and hour, found by its city written with spaces and by its offset. */
function rowOf(zone: string, now: Date, group: string): SelectItem {
  const clock = clockIn(zone, now);
  return { value: zone, label: zone, detail: clock ?? "This browser knows no zone of that name", group, keywords: `${zone.replace(/_/g, " ")} ${clock ?? ""}` };
}

export function ZoneEditor({ initial, saving, refused, onClose, onSave }: { initial: string; saving: boolean; refused: string | null; onClose: () => void; onSave: (zone: string) => Promise<boolean> }): ReactNode {
  const [zone, setZone] = useState(initial);
  // The hours are read once as the panel opens: a list of four hundred clocks is not kept ticking.
  const items = useMemo((): SelectItem[] => {
    const now = new Date();
    const kept = initial !== "" && initial !== HERE && !ZONES.includes(initial) ? [rowOf(initial, now, "Set now")] : [];
    const rest = ZONES.filter((one) => one !== HERE).map((one) => rowOf(one, now, one.includes("/") ? one.slice(0, one.indexOf("/")) : "Other"));
    return [{ value: "", label: "Not set", detail: "The agent is told the day, and no hour." }, ...kept, rowOf(HERE, now, "This browser's"), ...rest];
  }, [initial]);
  return (
    <EditDialog title="Time zone" icon="clock" about="Every call opens told the day, the weekday and the hour in this zone. With none, the agent is told the day only and cannot say what time it is." saving={saving} refused={refused} onClose={onClose} onSave={() => void onSave(zone)}>
      <Field label="Time zone">
        <Select items={items} value={zone} label="Time zone" searchable searchPlaceholder="Search a city, a region or an offset" onChange={setZone} />
      </Field>
    </EditDialog>
  );
}
