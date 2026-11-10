/** Slowest turns: the replies that kept a caller waiting longest, each a row that opens where its wait went in the side panel, with the way into its call. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { ago, percent } from "../lib/format";
import { SidePanel } from "../ui/side-panel";
import type { SlowTurn } from "./door";
import { slowPartsOf, took, type Part } from "./fold";

const WIDTH = 420;

const sameTurn = (a: SlowTurn, b: SlowTurn | null): boolean => b !== null && a.call === b.call && a.seq === b.seq;

function Bar({ parts }: { parts: readonly Part[] }): ReactNode {
  return (
    <span className="ob-bar" aria-hidden="true">
      {parts.map((part) => (
        <span key={part.stage} className={`ob-tone-${part.tone}`} style={{ flexGrow: part.seconds }} />
      ))}
    </span>
  );
}

// The longest part is the one worth saying: it is where the caller waited.
function longestOf(parts: readonly Part[]): Part | undefined {
  return [...parts].sort((a, b) => b.seconds - a.seconds)[0];
}

export function SlowTurns({ turns, open, onOpen }: { turns: readonly SlowTurn[]; open: SlowTurn | null; onOpen: (turn: SlowTurn) => void }): ReactNode {
  return (
    <section className="dash-card ob-card" aria-label="Slowest turns">
      <div className="dash-card-top ob-card-top">
        <span className="dash-eyebrow">Slowest turns</span>
        <span className="dash-quiet ob-clip">Open one to see where its wait went</span>
      </div>
      {turns.length === 0 ? (
        <p className="dash-empty">No turn was timed in these days.</p>
      ) : (
        <div className="dash-rows">
          {turns.map((turn) => {
            const parts = slowPartsOf(turn);
            const longest = longestOf(parts);
            const on = sameTurn(turn, open);
            return (
              <button key={`${turn.call}-${turn.seq}`} type="button" className={on ? "ob-row ob-slow dash-row ob-row-on" : "ob-row ob-slow dash-row"} aria-pressed={on} onClick={() => onOpen(turn)}>
                <span className="ob-row-main">
                  <span className="ob-row-name ob-clip">{turn.name ?? "A caller"}</span>
                  <span className="ob-row-under ob-clip">
                    {turn.agent}, {ago(turn.at)}
                    {longest !== undefined && `, ${longest.doing.toLowerCase()} took ${took(longest.seconds)}`}
                  </span>
                </span>
                {parts.length > 0 && (
                  <span className="ob-slow-bar">
                    <Bar parts={parts} />
                  </span>
                )}
                <span className="ob-num ob-slow-took">{took(turn.e2e_s)}</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function whenSaid(at: number): string {
  return new Date(at * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function SlowTurnPanel({ turn, onClose }: { turn: SlowTurn; onClose: () => void }): ReactNode {
  const parts = slowPartsOf(turn);
  const sum = parts.reduce((all, part) => all + part.seconds, 0);
  const longest = longestOf(parts);
  const footer = (
    <Link to={`/calls/${encodeURIComponent(turn.call)}`} className="ob-open-call">
      Open the call
    </Link>
  );
  return (
    <SidePanel title="A slow turn" icon="clock" about={`${turn.name ?? "A caller"} waited ${took(turn.e2e_s)} for the agent's first sound.`} footer={footer} width={WIDTH} onClose={onClose}>
      <dl className="ob-facts">
        <div>
          <dt>Agent</dt>
          <dd className="ob-clip">{turn.agent}</dd>
        </div>
        <div>
          <dt>When</dt>
          <dd>{whenSaid(turn.at)}</dd>
        </div>
        <div>
          <dt>Line of the call</dt>
          <dd>{turn.seq}</dd>
        </div>
      </dl>

      <div className="ob-detail">
        <span className="dash-eyebrow">Where the wait went</span>
        {parts.length === 0 ? (
          <p className="dash-quiet">The stages of this turn were not timed one by one.</p>
        ) : (
          <>
            <Bar parts={parts} />
            <div className="ob-detail-parts">
              {parts.map((part) => (
                <div key={part.stage} className="ob-detail-part">
                  <span className={`ob-swatch ob-tone-${part.tone}`} aria-hidden="true" />
                  <span className="ob-detail-name ob-clip">{part.name}</span>
                  <span className="dash-quiet ob-num">{percent(part.seconds / sum)}</span>
                  <span className="ob-num">{took(part.seconds)}</span>
                </div>
              ))}
            </div>
            {longest !== undefined && (
              <p className="dash-quiet">
                {longest.doing} took {took(longest.seconds)}, the longest part of the wait.
              </p>
            )}
          </>
        )}
      </div>
    </SidePanel>
  );
}
