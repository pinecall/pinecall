/** Rates: what each model costs in US dollars, by the unit it is billed in. Every call's cost, and every budget, is read off them. */

import { useCallback, useState, type ReactNode } from "react";

import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { useMove } from "../numbers/parts";
import { Icon } from "../shell/icons";
import { Field } from "../ui/setting";
import { RATE_UNITS, type ProvidersRow, type Rate, type RateUnit } from "./settings-door";
import { Effect, Refusal, Section } from "./settings-parts";

const SHOWN_AT_ONCE = 30;

const UNITS: Record<RateUnit, string> = {
  input: "Input, per million tokens",
  output: "Output, per million tokens",
  cached_input: "Cached input, per million tokens",
  cache_creation: "Cache write, per million tokens",
  characters: "Per character spoken",
  audio_seconds: "Per second of audio",
  minutes: "Per minute",
};

/** `0.3` → "0.30", `2` → "2", `0.0078` → "0.0078": dollars as a price list writes them. */
function dollars(value: number): string {
  if (value < 0.01) return String(Number(value.toPrecision(3)));
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

/** A rate in a few words, in the units people compare prices in. */
function rateSaid(rate: Rate): string {
  const parts: string[] = [];
  if (rate.input != null || rate.output != null) parts.push(`$${dollars(rate.input ?? 0)} in · $${dollars(rate.output ?? 0)} out per 1M tokens`);
  if (rate.characters != null) parts.push(`$${dollars(rate.characters * 1_000_000)} per 1M characters`);
  if (rate.audio_seconds != null) parts.push(`$${dollars(rate.audio_seconds * 60)} per minute of audio`);
  if (rate.minutes != null) parts.push(`$${dollars(rate.minutes)} per minute`);
  return parts.length === 0 ? "No price: calls on it are counted as free" : parts.join(" · ");
}

/** `model` null is a new price: the model's id, or the start of one, is typed first. */
function RatePanel({ model, was, taken, saving, refused, onSave, onClose }: { model: string | null; was: Rate; taken: readonly string[]; saving: boolean; refused: string | null; onSave: (model: string, rate: Rate) => void; onClose: () => void }): ReactNode {
  const [named, setNamed] = useState(model ?? "");
  const [typed, setTyped] = useState<Record<RateUnit, string>>(() => Object.fromEntries(RATE_UNITS.map((unit) => [unit, was[unit] == null ? "" : String(was[unit])])) as Record<RateUnit, string>);
  const [wrong, setWrong] = useState<string | null>(null);
  const save = (): void => {
    if (named === "") return setWrong("Type the model's id, or the start of one.");
    if (model === null && taken.includes(named)) return setWrong(`${named} already has a price. Change that one.`);
    const bad = RATE_UNITS.find((unit) => typed[unit].trim() !== "" && (Number.isNaN(Number(typed[unit])) || Number(typed[unit]) < 0));
    if (bad !== undefined) return setWrong(`${UNITS[bad]}: a number of dollars, or empty.`);
    setWrong(null);
    const prices = Object.fromEntries(RATE_UNITS.map((unit) => [unit, typed[unit].trim() === "" ? null : Number(typed[unit])]));
    onSave(named, { ...was, ...prices, as_of: new Date().toISOString().slice(0, 10) });
  };
  return (
    <EditDialog title={model ?? "Price a model"} icon="coins" about="US dollars, in the unit the vendor bills in. Leave a unit empty when the model is not billed that way." saving={saving} refused={wrong ?? refused} onSave={save} onClose={onClose}>
      <Effect>Calls on this model are costed at these prices from the next one, for every organization: what Usage shows, and what a spend cap counts. Calls already made keep the cost they had.</Effect>
      {model === null && (
        <Field label="Model">
          <input className="cfg-input" aria-label="Model" placeholder="gemini-3.5-flash" spellCheck={false} autoFocus value={named} onChange={(event) => setNamed(event.target.value.trim())} />
          <p className="dash-quiet">A price covers every model whose id starts with what you type, so a family prices its dated versions. The longest match wins.</p>
        </Field>
      )}
      <div className="bxs-limits">
        {RATE_UNITS.map((unit) => (
          <label key={unit} className="bxs-limit">
            <span className="bxs-limit-name">{UNITS[unit]}</span>
            <input className="cfg-input" inputMode="decimal" aria-label={UNITS[unit]} placeholder="Not billed" value={typed[unit]} onChange={(event) => setTyped({ ...typed, [unit]: event.target.value })} />
          </label>
        ))}
      </div>
    </EditDialog>
  );
}

export function DefaultRates({ row, write }: { row: ProvidersRow; write: (next: ProvidersRow) => Promise<void> }): ReactNode {
  const acting = useMove();
  const [query, setQuery] = useState("");
  // "" is a new price, a key the one being changed.
  const [open, setOpen] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const keys = Object.keys(row.rates).sort();
  const found = keys.filter((key) => key.toLowerCase().includes(query.trim().toLowerCase()));
  const shown = found.slice(0, SHOWN_AT_ONCE);
  const put = (model: string, rate: Rate | null): Promise<void> => {
    const rates = { ...row.rates };
    if (rate === null) delete rates[model];
    else rates[model] = rate;
    return acting.move(() => write({ ...row, rates }));
  };

  return (
    <>
      <Section
        icon="coins"
        title="Rates"
        about="What each model costs. A call's cost in Usage, and every spend cap, is computed from these. A model with no price is counted as free."
        action={
          <button type="button" className="cfg-save tst-action" onClick={() => setOpen("")}>
            <Icon name="plus" size={12} />
            Price a model
          </button>
        }
      >
        {open === null && <Refusal>{acting.refused}</Refusal>}
        <div className="tst-tools">
          <label className="tst-search">
            <Icon name="search" size={14} />
            <input aria-label="Search models" placeholder={`Search ${keys.length} priced models`} spellCheck={false} value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>
        {shown.map((key) => {
          const rate = row.rates[key] ?? {};
          return (
            <div key={key} className="tst-row bxs-row">
              <span className="tst-row-words">
                <span className="tst-row-name bxs-code dash-clip">{key}</span>
                <span className="tst-row-under dash-clip">{rateSaid(rate)}</span>
              </span>
              {rate.as_of != null && <span className="tst-row-when">Since {rate.as_of}</span>}
              <span className="bxs-acts">
                <button type="button" className="app-button" onClick={() => setOpen(key)}>
                  Change
                </button>
                <ConfirmButton label="Remove" asks="Count it as free?" danger onConfirm={() => void put(key, null).catch(() => undefined)} />
              </span>
            </div>
          );
        })}
        {found.length === 0 && <p className="dash-quiet tst-none">{keys.length === 0 ? "No model is priced: every call costs nothing on paper." : "No priced model by that name."}</p>}
        {found.length > shown.length && <p className="dash-quiet tst-none">{found.length - shown.length} more. Search to find one.</p>}
      </Section>
      {open !== null && <RatePanel key={open} model={open === "" ? null : open} was={open === "" ? {} : (row.rates[open] ?? {})} taken={keys} saving={acting.busy} refused={acting.refused} onSave={(model, rate) => void put(model, rate).then(close, () => undefined)} onClose={close} />}
    </>
  );
}
