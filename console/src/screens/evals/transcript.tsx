/** A golden drawn as a transcript: one block per turn — the caller's line or the backend's fact, and under it each step with its state — then the final checks. */

import type { ReactNode } from "react";

import { Pill, type Tone } from "../../ui";
import { valueWords, type Input, type Line, type Read, type State } from "./golden-words";
import "./evals.css";

const TONE: Record<State, Tone> = { held: "green", broke: "red", skipped: "muted", "not played": "muted" };

/** The state as a mark, in its one word. */
export function StateMark({ state }: { state: State }): ReactNode {
  return (
    <Pill tone={TONE[state]} small>
      {state}
    </Pill>
  );
}

export function Transcript({ read }: { read: Read }): ReactNode {
  return (
    <div className="ev-tx">
      <ol className="ev-tx-turns">
        {read.turns.map((turn) => (
          <li key={turn.number} className={turn.state === "not played" ? "ev-tx-turn ev-tx-turn-off" : turn.state === "broke" ? "ev-tx-turn ev-tx-turn-broke" : "ev-tx-turn"}>
            <div className="ev-tx-in">
              <span className="ev-tx-n">{turn.number}</span>
              <InputSaid input={turn.input} number={turn.number} />
              {turn.state === "not played" && <StateMark state="not played" />}
            </div>
            {turn.lines.length > 0 && (
              <ul className="ev-tx-lines">
                {turn.lines.map((line, at) => (
                  <LineSaid key={`${String(at)}-${line.said}`} line={line} />
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      {read.finals.length > 0 && (
        <div className="ev-tx-end">
          <div className="ev-tx-end-head">At the end</div>
          <ul className="ev-tx-lines">
            {read.finals.map((line, at) => (
              <LineSaid key={`${String(at)}-${line.said}`} line={line} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function InputSaid({ input, number }: { input: Input; number: number }): ReactNode {
  if (input === null) return <span className="ev-tx-event">turn {number}</span>;
  if ("say" in input) return <span className="ev-tx-say">“{input.say}”</span>;
  const data = Object.entries(input.data).map(([key, value]) => `${key} ${valueWords(value)}`);
  return (
    <span className="ev-tx-event">
      your backend sends <code>{input.event}</code>
      {data.length > 0 && ` · ${data.join(", ")}`}
    </span>
  );
}

function LineSaid({ line }: { line: Line }): ReactNode {
  return (
    <li className="ev-tx-line">
      <span className="ev-tx-said">{line.said}</span>
      {line.state !== undefined && <StateMark state={line.state} />}
      {line.why !== undefined && <span className="ev-tx-why">{line.why}</span>}
    </li>
  );
}
