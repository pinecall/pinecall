/** Slowest turns: the replies that kept a caller waiting longest in the window, each with where its time went and the call it is in. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { rowAt } from "../../lib/harness";
import type { SlowTurn } from "../../lib/slow";
import { Card, CardHead } from "../../ui";

const seconds = (value: number): string => (value < 1 ? `${Math.round(value * 1000)} ms` : `${value.toFixed(2)} s`);

/** The parts of a turn in the order it happens, as the bar and the sentence under it say them. */
function partsOf(turn: SlowTurn): { key: "hears" | "thinks" | "tools" | "speaks"; took: number; said: string }[] {
  const parts = [
    { key: "hears", took: turn.hears_s, said: "Hearing" },
    { key: "thinks", took: turn.thinks_s, said: "Thinking" },
    { key: "tools", took: turn.tools_s, said: "The tools" },
    { key: "speaks", took: turn.speaks_s, said: "Speaking" },
  ] as const;
  return parts.flatMap((part) => (part.took === null || part.took <= 0 ? [] : [{ key: part.key, took: part.took, said: part.said }]));
}

export function SlowTurns({ turns, agent }: { turns: readonly SlowTurn[]; agent: string }): ReactNode {
  return (
    <Card>
      <CardHead title="Slowest turns" meta="click to open the call" />
      {turns.length === 0 ? (
        <p className="obs-quiet obs-quiet-card">No turn was timed in these days.</p>
      ) : (
        turns.map((turn) => {
          const parts = partsOf(turn);
          const sum = parts.reduce((all, part) => all + part.took, 0);
          // The longest part is the one worth saying: it is where the caller waited.
          const longest = [...parts].sort((a, b) => b.took - a.took)[0];
          return (
            <Link key={`${turn.call}-${turn.seq}`} to={`${rowAt(agent, "calls")}/${turn.call}#seq-${turn.seq}`} className="obs-slow">
              <div className="obs-slow-top">
                <span className="obs-slow-who">
                  {turn.name ?? "A caller"} <span className="obs-slow-where">· {turn.agent} · #{turn.seq}</span>
                </span>
                <span className="obs-slow-took">{seconds(turn.e2e_s)}</span>
              </div>
              {sum > 0 && (
                <div className="obs-slow-bar" aria-hidden>
                  {parts.map((part) => (
                    <span key={part.key} className={`obs-part-${part.key}`} style={{ width: `${(part.took / sum) * 100}%` }} />
                  ))}
                </div>
              )}
              {longest !== undefined && (
                <span className="obs-slow-why">
                  {longest.said} took {seconds(longest.took)}
                </span>
              )}
            </Link>
          );
        })
      )}
    </Card>
  );
}
