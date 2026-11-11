/** The agent's time zone, picked from the zones this browser knows: the clock its calls open on. */

import { useId, useState, type ReactNode } from "react";

import { EditDialog } from "./dialog";

// Every IANA zone the browser knows; one it does not list can still be typed, and the gateway checks it.
const ZONES: readonly string[] = Intl.supportedValuesOf("timeZone");
const HERE = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** The hour it is in a zone now, or null for a name that is no zone. */
function nowIn(zone: string): string | null {
  try {
    return new Intl.DateTimeFormat(undefined, { timeZone: zone, weekday: "long", hour: "numeric", minute: "2-digit" }).format(new Date());
  } catch {
    return null;
  }
}

export function ZoneEditor({ initial, saving, refused, onClose, onSave }: { initial: string; saving: boolean; refused: string | null; onClose: () => void; onSave: (zone: string) => Promise<boolean> }): ReactNode {
  const [zone, setZone] = useState(initial);
  const list = useId();
  const typed = zone.trim();
  const clock = typed === "" ? null : nowIn(typed);
  return (
    <EditDialog title="Time zone" about="Every call opens told the day, the weekday and the hour in this zone. With none, the agent is told the day only and cannot say what time it is." saving={saving} refused={refused} onClose={onClose} onSave={() => void onSave(typed)}>
      <label className="cfg-field">
        An IANA zone: America/Montevideo, Europe/Madrid
        <input className="cfg-input" value={zone} list={list} autoFocus spellCheck={false} onChange={(event) => setZone(event.target.value)} />
        <datalist id={list}>
          {ZONES.map((one) => (
            <option key={one} value={one} />
          ))}
        </datalist>
      </label>
      <p className="dash-quiet">{typed === "" ? "Empty takes the zone out." : clock === null ? "This browser knows no zone of that name." : `There it is ${clock} now.`}</p>
      {typed !== HERE && (
        <button type="button" className="cfg-zone-here" onClick={() => setZone(HERE)}>
          Use this browser's zone, {HERE}
        </button>
      )}
    </EditDialog>
  );
}
