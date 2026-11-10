/** An org's limits in the page's words, and the fields that type them: the ones a new org is admitted with and the ones an org already has. */

import type { ReactNode } from "react";

import type { Quota, Shape } from "./settings-door";
import "../configure/configure.css";
import "./settings.css";

export const ABOUT: Record<Quota | Shape, { name: string; about: string; unit: string }> = {
  minutes: { name: "Call minutes", about: "Minutes of spoken calls, each month.", unit: "a month" },
  messages: { name: "Chat messages", about: "Written turns, each month.", unit: "a month" },
  llm_tokens: { name: "Model tokens", about: "What its agents read and write, each month.", unit: "a month" },
  concurrent_calls: { name: "Calls at once", about: "Calls on the line at the same moment.", unit: "at once" },
  agents: { name: "Agents", about: "How many agents it may have.", unit: "" },
  numbers: { name: "Phone numbers", about: "Numbers bought through this deployment.", unit: "" },
  seats: { name: "People", about: "Members, invited or active.", unit: "" },
  hosted_apps: { name: "Hosted apps", about: "Apps and Studio agents this deployment runs for it.", unit: "" },
  memory_facts: { name: "Remembered facts", about: "What its agents remember about callers.", unit: "" },
  knowledge_chunks: { name: "Knowledge", about: "Pieces of text indexed from its documents.", unit: "pieces" },
  evals: { name: "Evaluations", about: "Judge verdicts on this deployment's keys, each month.", unit: "a month" },
  simulations: { name: "Simulated calls", about: "Test calls played by a pretend caller, each month.", unit: "a month" },
  budget_usd: { name: "Spend cap", about: "Dollars a month, both environments together.", unit: "USD a month" },
  simulations_at_once: { name: "Simulated calls at once", about: "Pretend callers on the line together.", unit: "at once" },
  comparison_calls: { name: "Calls in one comparison", about: "The most one comparison may place.", unit: "" },
};

/** What was typed as the door takes it: an empty field is null, which is no limit; zero is a limit that refuses everything. */
export function typedLimit(text: string | undefined): number | null {
  return text === undefined || text === "" ? null : Number(text);
}

/** One field per limit, digits only; `typed` holds each as text so an empty one stays empty. */
export function LimitFields({ names, typed, placeholder, onType }: { names: readonly (Quota | Shape)[]; typed: Record<string, string>; placeholder: string; onType: (typed: Record<string, string>) => void }): ReactNode {
  return (
    <div className="bxs-limits">
      {names.map((name) => (
        <label key={name} className="bxs-limit">
          <span className="bxs-limit-name">{ABOUT[name].name}</span>
          <input className="cfg-input" inputMode="numeric" aria-label={ABOUT[name].name} placeholder={placeholder} value={typed[name] ?? ""} onChange={(event) => onType({ ...typed, [name]: event.target.value.replace(/[^0-9]/g, "") })} />
          <span className="dash-quiet">{ABOUT[name].about}</span>
        </label>
      ))}
    </div>
  );
}
