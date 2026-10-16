/** Renders a metrics block field by field, under LiveKit's own names (never renamed). */

import type { ReactNode } from "react";

import type { Reading } from "@pinecall/core/metrics";

// Units not drawn: the value itself says what it is.
const NOT_A_UNIT = new Set(["tag", "name", "id", "flag"]);

export function Readings({ rows }: { rows: Reading[] }): ReactNode {
  return (
    <div className="call-readings">
      {rows.map((reading) => (
        <div key={reading.field} className="call-reading">
          <span className="call-reading-name">{reading.field}</span>
          <span className="call-reading-value" title={String(reading.value)}>
            {rounded(String(reading.value))}
            {reading.unit !== null && !NOT_A_UNIT.has(reading.unit) && <span className="call-seen"> {reading.unit}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

// Floats round to 3 decimals; the full value is in the hover title.
function rounded(value: string): string {
  return /^-?\d+\.\d{4,}$/.test(value) ? Number(value).toFixed(3) : value;
}
