/** What each model costs, in US dollars by the unit it is billed in: the price every call's cost is read off. */

import { useState, type ReactNode } from "react";

import { Button, Card, CardHead, Input, TextAction } from "../../ui";
import { RATE_UNITS, type Rate, type RateUnit } from "./door-providers";

const UNIT_SAID: Record<RateUnit, string> = {
  input: "input / M tok",
  output: "output / M tok",
  cached_input: "cached / M tok",
  cache_creation: "cache write / M tok",
  characters: "/ char",
  audio_seconds: "/ audio s",
  minutes: "/ min",
};

/** A typed price back into the rate: empty leaves the unit out, so it is not billed. */
export function withPrice(rate: Rate, unit: RateUnit, typed: string): Rate {
  const next: Rate = { ...rate };
  const value = typed.trim() === "" ? null : Number(typed);
  if (value === null || Number.isNaN(value)) delete next[unit];
  else next[unit] = value;
  return next;
}

/**
 * A key prices every model whose id starts with it, the longest winning, so a family prices its
 * dated snapshots. A model no key prices is listed unpriced, never at zero.
 */
export function DefaultRates({ rates, onChange }: { rates: Record<string, Rate>; onChange: (rates: Record<string, Rate>) => void }): ReactNode {
  const [model, setModel] = useState("");
  const keys = Object.keys(rates).sort();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <Card>
      <CardHead title="Prices" meta="US dollars · a key prices every model id that starts with it · empty is not billed" />
      <div className="box-rates">
        <div className="box-rate box-rate-head">
          <span>model</span>
          {RATE_UNITS.map((unit) => (
            <span key={unit}>{UNIT_SAID[unit]}</span>
          ))}
          <span>since</span>
          <span />
        </div>
        {keys.map((key) => {
          const rate = rates[key] ?? {};
          return (
            <div key={key} className="box-rate">
              <span className="box-mono" title={key}>
                {key}
              </span>
              {RATE_UNITS.map((unit) => (
                <Input
                  key={unit}
                  inputMode="decimal"
                  value={rate[unit] === undefined || rate[unit] === null ? "" : String(rate[unit])}
                  onChange={(event) => onChange({ ...rates, [key]: { ...withPrice(rate, unit, event.target.value), as_of: today } })}
                />
              ))}
              <span className="box-limit-about">{rate.as_of ?? ""}</span>
              <TextAction
                danger
                onClick={() => {
                  const next = { ...rates };
                  delete next[key];
                  onChange(next);
                }}
              >
                Remove
              </TextAction>
            </div>
          );
        })}
      </div>
      <div className="box-line">
        <Input value={model} placeholder="a model id, or the start of one: gemini-3.5-flash" onChange={(event) => setModel(event.target.value.trim())} />
        <Button
          size="md"
          disabled={model === "" || model in rates}
          onClick={() => {
            onChange({ ...rates, [model]: { as_of: today } });
            setModel("");
          }}
        >
          Price a model
        </Button>
      </div>
    </Card>
  );
}
