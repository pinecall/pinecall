/** One agent's goldens on the Goldens page: its name and how they stand, the way to its Test tab, and a row per golden. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { ago } from "../lib/format";
import { Icon } from "../shell/icons";
import { fromOf } from "../test/golden-panel";
import { goldenPath, playableIn, tallyOf, testTabOf, type Agent, type Row, type Tally } from "./fold";

/** How many stand how, as one slim bar. */
export function Standing({ tally, wide = false }: { tally: Tally; wide?: boolean }): ReactNode {
  return (
    <span className={wide ? "gd-bar gd-bar-wide" : "gd-bar"} role="img" aria-label={`${tally.held} held, ${tally.broke} broke, ${tally.none} not run`}>
      {tally.held > 0 && <i className="gd-bar-held" style={{ flexGrow: tally.held }} />}
      {tally.broke > 0 && <i className="gd-bar-broke" style={{ flexGrow: tally.broke }} />}
      {tally.none > 0 && <i className="gd-bar-none" style={{ flexGrow: tally.none }} />}
    </span>
  );
}

function Status({ row, playing }: { row: Row; playing: boolean }): ReactNode {
  const verdict = playing ? "playing" : (row.result?.verdict ?? "none");
  const said = verdict === "playing" ? "Playing…" : verdict === "held" ? "Held" : verdict === "broke" ? "Broke" : "Not run";
  return (
    <span className={`gd-status gd-status-${verdict}`} title={said}>
      <span className="gd-status-words">{said}</span>
    </span>
  );
}

function GoldenRow({ agent, row, search, on, playing, busy, authors, onRun }: { agent: string; row: Row; /** The address's query, kept as a golden opens. */ search: string; on: boolean; playing: boolean; busy: boolean; authors: ReadonlyMap<string, string>; onRun: () => void }): ReactNode {
  const { kept, result } = row;
  return (
    <div className={on ? "gd-row gd-row-on" : "gd-row"}>
      <Link to={`${goldenPath(agent, row.name)}${search}`} className="gd-row-main" aria-current={on ? "true" : undefined}>
        <span className="gd-mark" aria-hidden="true">
          <Icon name="goldens" size={14} />
        </span>
        <span className="gd-row-words">
          <span className="gd-row-name">
            <span className="dash-clip">{row.name}</span>
            {kept === null && <span className="dash-tag gd-tag">in code</span>}
            {kept?.held_out === true && <span className="dash-tag gd-tag">held out</span>}
          </span>
          <span className="gd-row-under dash-clip">{kept === null ? "Lives in the app's code" : fromOf(kept, authors)}</span>
        </span>
        <span className="gd-row-when">{result === undefined || playing ? "" : ago(result.at)}</span>
        <Status row={row} playing={playing} />
      </Link>
      <span className="gd-row-acts">
        {kept !== null && (
          <button type="button" className="gd-run" disabled={busy} aria-label={`Run ${row.name}`} title={busy ? "A run is on" : "Run it"} onClick={onRun}>
            <Icon name="play" size={13} />
          </button>
        )}
      </span>
    </div>
  );
}

export interface GroupProps {
  agent: Agent;
  /** Every golden of the agent; null while it is read. */
  rows: readonly Row[] | null;
  /** The ones the search and the filter leave. */
  shown: readonly Row[];
  filtered: boolean;
  refused: string | null;
  search: string;
  /** The golden open, when it is this agent's. */
  open: string | null;
  /** The goldens of this agent a run is playing now. */
  playing: ReadonlySet<string> | null;
  /** A run is on, this agent's or another's: the next waits for it. */
  busy: boolean;
  authors: ReadonlyMap<string, string>;
  onRun: (names: readonly string[]) => void;
  onNew: () => void;
}

export function Group({ agent, rows, shown, filtered, refused, search, open, playing, busy, authors, onRun, onNew }: GroupProps): ReactNode {
  const tally = rows === null ? null : tallyOf(rows);
  const playable = rows === null ? [] : playableIn(rows);
  const whyNoRun = busy ? "A run is on" : rows !== null && rows.length > 0 && playable.length === 0 ? "None of these is played from here: they are held out, or live in the app's code" : undefined;
  return (
    <section className="dash-card gd-group" aria-label={`Goldens of ${agent.slug}`}>
      <header className="gd-group-head">
        <h2 className="gd-group-name dash-clip">{agent.slug}</h2>
        {tally !== null && rows !== null && rows.length > 0 && (
          <span className="gd-stands">
            <Standing tally={tally} />
            <span>
              {tally.held} of {rows.length} hold
            </span>
          </span>
        )}
        <span className="gd-group-acts">
          <Link to={testTabOf(agent)} className="app-button gd-action" title={`Open the Test tab of ${agent.slug}`}>
            Test tab
          </Link>
          <button type="button" className="app-button gd-action" onClick={onNew}>
            <Icon name="plus" size={12} />
            New
          </button>
          {playable.length > 0 && (
            <button type="button" className="cfg-save gd-action" disabled={busy} title={whyNoRun} onClick={() => onRun(playable)}>
              <Icon name="play" size={11} />
              {playing !== null ? "Playing…" : "Run all"}
            </button>
          )}
        </span>
      </header>
      {refused !== null && <p className="gd-refused">{refused}</p>}
      {rows === null && <p className="dash-quiet gd-quiet">Reading…</p>}
      {rows !== null && rows.length === 0 && refused === null && <p className="dash-quiet gd-quiet">No golden yet.</p>}
      {rows !== null && rows.length > 0 && shown.length === 0 && <p className="dash-quiet gd-quiet">{filtered ? "None of its goldens matches." : "No golden yet."}</p>}
      {shown.map((row) => (
        <GoldenRow key={row.kept?.id ?? `code:${row.name}`} agent={agent.slug} row={row} search={search} on={open === row.name} playing={playing?.has(row.name) === true} busy={busy} authors={authors} onRun={() => onRun([row.name])} />
      ))}
    </section>
  );
}
