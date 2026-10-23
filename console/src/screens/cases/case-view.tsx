/** One case, read: what broke, the call as it will be played again with what it checks at the end, and what to do. */

import type { ReactNode } from "react";

import { dayAndTime } from "../../lib/format";
import { inTheWorld } from "../../lib/mode";
import { Pill } from "../../ui";
import { finalChecks, readGolden, Transcript } from "../evals";
import { CaseRun } from "./case-run";
import { Decide } from "./decide";
import type { EvalCase } from "./door";
import { FixIt } from "./fix-it";
import { Section } from "./section";

const STATUS_TONE = { pending: "amber", approved: "green", dismissed: "gray" } as const;

const STATUS_SAID = { pending: "waiting for you", approved: "played every night", dismissed: "dismissed" } as const;

export function CaseView({ agent, kept, onDecided }: { agent: string; kept: EvalCase; onDecided: (kept: EvalCase) => void }): ReactNode {
  const golden = kept.golden;
  const state = flattened(golden.state ?? {});
  return (
    <article className="cs-doc">
      <header className="cs-doc-head">
        <div>
          <h1 className="cs-doc-name">{kept.name}</h1>
          <p className="cs-doc-about">
            <Pill tone={STATUS_TONE[kept.status]}>{STATUS_SAID[kept.status]}</Pill>
            {kept.kept_in_repo && <Pill tone="indigo">in the repository</Pill>}
          </p>
        </div>
        <Decide kept={kept} onDecided={onDecided} />
      </header>

      <Section title="What broke">
        {kept.broke.length === 0 ? (
          <p className="cs-none">{kept.source === "person" ? "Nothing: a person wrote this case." : "Nothing: a person kept this call."}</p>
        ) : (
          <ul className="cs-broke">
            {kept.broke.map((one) => (
              <li key={one.judge}>
                <Pill tone="red">{one.judge}</Pill>
                <span>{one.reason}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="The call, as it will be played again">
        {state.length > 0 && (
          <dl className="cs-facts">
            {state.map(([what, value]) => (
              <div key={what} className="cs-fact">
                <dt>{what}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {(golden.memory ?? []).length > 0 && <p className="cs-memory">Memory recalled: {(golden.memory ?? []).join(" · ")}</p>}
        {golden.today !== undefined && golden.today !== null && <p className="cs-memory">Played as if today were {golden.today}.</p>}
        <Transcript read={readGolden(golden)} />
        {finalChecks(golden.expect ?? {}).length === 0 && <p className="cs-none">Nothing is checked at the end yet: write what the agent must keep doing.</p>}
      </Section>

      <FixIt agent={agent} kept={kept} />
      <CaseRun agent={agent} kept={kept} />

      <footer className="cs-doc-foot">
        {kept.source === "person" ? (
          <>Written by {kept.author}, {dayAndTime(kept.created_at)}, in the {kept.source_env}.</>
        ) : (
          <>
            Kept {kept.author === "the hang-up panel" ? "at hang-up" : `by ${kept.author}`}, {dayAndTime(kept.created_at)}, from a{" "}
            <a href={inTheWorld(kept.source_env, `/calls/${encodeURIComponent(kept.source_call)}`)}>{kept.source_env} call</a>
            {kept.source_version !== null && ` on settings v${kept.source_version}`}.
          </>
        )}
        {kept.decided_by !== null && ` Decided by ${kept.decided_by}.`}
      </footer>
    </article>
  );
}

// One level of a state's objects opened into dotted names (`patient.name`), the rest said as JSON.
function flattened(state: Record<string, unknown>): [string, string][] {
  return Object.entries(state).flatMap(([what, value]): [string, string][] =>
    value !== null && typeof value === "object" && !Array.isArray(value)
      ? Object.entries(value).map(([inner, said]): [string, string] => [`${what}.${inner}`, typeof said === "string" ? said : JSON.stringify(said)])
      : [[what, typeof value === "string" ? value : JSON.stringify(value)]],
  );
}
