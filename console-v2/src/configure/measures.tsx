/** How long a turn takes, drawn as the road from the caller's last word to the agent's first, and a figure with what it is made of, as a ring. */

import type { ReactNode } from "react";

import { milliseconds, perMinute } from "./stages";
import "./configure.css";

type Tone = "accent" | "blue" | "pink" | "warn" | "good";

export interface Slice {
  name: string;
  value: number | null;
  tone: Tone;
}

function Road({ total, calls, steps }: { total: number | null; calls: number; steps: readonly Slice[] }): ReactNode {
  return (
    <div className="cfg-measure">
      <span className="dash-eyebrow">Response time</span>
      <p className="cfg-figure">
        {total === null ? "—" : `${total.toFixed(2)} s`}
        <span className="dash-quiet">{calls === 0 ? "no calls yet" : `median of ${calls} calls`}</span>
      </p>
      <div className="cfg-road">
        {steps.map((step) => (
          <div key={step.name} className={`cfg-step cfg-tone-${step.tone}`} style={{ flexGrow: step.value ?? 1 }}>
            <span className="cfg-step-rail" aria-hidden="true" />
            <span className="cfg-step-name">{step.name}</span>
            <span className="dash-quiet">{milliseconds(step.value)}</span>
          </div>
        ))}
      </div>
      <div className="cfg-road-ends dash-quiet">
        <span>Caller stops</span>
        <span>Agent speaks</span>
      </div>
    </div>
  );
}

function ringOf(slices: readonly Slice[]): string {
  const whole = slices.reduce((sum, one) => sum + (one.value ?? 0), 0);
  if (whole === 0) return "var(--raised)";
  let at = 0;
  const stops = slices.map((one) => {
    const from = at;
    at += ((one.value ?? 0) / whole) * 100;
    return `var(--${one.tone}) ${from}% ${at}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

export function Ring({ title, figure, note, slices }: { title: string; figure: string; note: string | null; slices: readonly (Slice & { shown: string })[] }): ReactNode {
  return (
    <div className="cfg-measure">
      <span className="dash-eyebrow">{title}</span>
      <div className="cfg-ring-row">
        <span className="cfg-ring" style={{ background: ringOf(slices) }} aria-hidden="true" />
        <div className="cfg-ring-words">
          <p className="cfg-figure">
            {figure}
            <span className="dash-quiet">{note}</span>
          </p>
          <dl className="cfg-legend">
            {slices.map((one) => (
              <div key={one.name}>
                <dt>
                  <span className={`cfg-swatch cfg-tone-${one.tone}`} aria-hidden="true" />
                  {one.name}
                </dt>
                <dd>{one.shown}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}

export function Measures({ total, calls, steps, rate, rateFrom, slices }: { total: number | null; calls: number; steps: readonly Slice[]; rate: number | null; rateFrom: string | null; slices: readonly Slice[] }): ReactNode {
  return (
    <div className="cfg-measures">
      <Road total={total} calls={calls} steps={steps} />
      <div className="cfg-measure-cost">
        <Ring title="Cost a minute" figure={rate === null ? "—" : `$${rate.toFixed(3)}`} note={rate === null ? "no minutes priced yet" : rateFrom} slices={slices.map((one) => ({ ...one, shown: perMinute(one.value) }))} />
      </div>
    </div>
  );
}
