/** Tools: what each of the agent's functions and webhooks did over the window — how often it ran, how often it worked, how long it took — and the error the failing ones last said. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { ago } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import type { ToolStat } from "../../lib/tools";
import { Card, CardHead } from "../../ui";

const COLUMNS = "minmax(0,1fr) 54px 64px 60px";

const took = (value: number | null): string => (value === null ? "—" : value < 1 ? `${Math.round(value * 1000)}ms` : `${value.toFixed(2)}s`);

/** Red when it never worked, amber when it sometimes did not, green when it always did. */
function toneOf(tool: ToolStat): "green" | "amber" | "red" {
  return tool.failed === 0 ? "green" : tool.failed >= tool.ran ? "red" : "amber";
}

export function ToolsCard({ tools, agent }: { tools: readonly ToolStat[]; agent: string }): ReactNode {
  return (
    <Card>
      <CardHead title="Tools" meta="your functions and webhooks" />
      {tools.length === 0 ? (
        <p className="obs-quiet obs-quiet-card">No tool ran in these days.</p>
      ) : (
        <>
          <div className="obs-tools-head" style={{ gridTemplateColumns: COLUMNS }}>
            <span>Tool</span>
            <span>Runs</span>
            <span>Worked</span>
            <span>p50</span>
          </div>
          {tools.map((tool) => {
            const tone = toneOf(tool);
            const worked = tool.ran === 0 ? null : (tool.ran - tool.failed) / tool.ran;
            return (
              <div key={tool.name} className="obs-tool">
                <div className="obs-tool-row" style={{ gridTemplateColumns: COLUMNS }}>
                  <span className="obs-tool-name">
                    <span className={`obs-dot-tone obs-tone-bg-${tone}`} aria-hidden />
                    <span className="obs-tool-word">{tool.name}</span>
                  </span>
                  <span className="obs-tool-runs">{tool.ran}</span>
                  <span className={`obs-tool-worked obs-tone-${tone}`}>{worked === null ? "—" : `${Math.round(worked * 100)}%`}</span>
                  <span className="obs-tool-took">{took(tool.median_s)}</span>
                </div>
                {tool.last_error !== null && (
                  <Link to={`${rowAt(agent, "calls")}/${tool.last_error.call}`} className="obs-tool-error">
                    {tool.last_error.text} · last {ago(tool.last_error.at)}
                  </Link>
                )}
              </div>
            );
          })}
        </>
      )}
    </Card>
  );
}
