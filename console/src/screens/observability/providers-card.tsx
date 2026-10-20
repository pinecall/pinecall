/** Providers: who hears, thinks and speaks for the agent, whose key runs them, how fast each answered, and whether that is past the line the org watches. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import type { SeriesVendor } from "../../lib/series";
import { Card, CardHead } from "../../ui";
import type { Monitor } from "../monitors";
import { readVendors } from "../providers";
import { stageOf } from "./answer";

const STAGES = [
  { stage: "stt", name: "Hears", monitor: null },
  { stage: "llm", name: "Thinks", monitor: "llm_median_s" },
  { stage: "tts", name: "Speaks", monitor: null },
] as const;

const took = (value: number): string => (value < 1 ? `${Math.round(value * 1000)}ms` : `${value.toFixed(2)}s`);

/** Slow only past a line the org drew for that stage; with none drawn, nothing is held against it. */
function standing(seconds: number, line: Monitor | undefined): "Healthy" | "Slow" {
  return line !== undefined && seconds > line.threshold ? "Slow" : "Healthy";
}

export function ProvidersCard({ vendors, monitors, agent }: { vendors: readonly SeriesVendor[]; monitors: readonly Monitor[]; agent: string }): ReactNode {
  const credentials = useCredentials();
  // The vendors the org runs on its own key; every other is lent by the runtime.
  const [own, setOwn] = useState<readonly string[]>([]);
  useEffect(() => {
    let gone = false;
    readVendors(credentials).then(
      (read) => !gone && setOwn(read),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return (
    <Card>
      <CardHead title="Providers" action={<Link to="/providers" className="ui-card-action">Manage keys</Link>} />
      {STAGES.map((one) => {
        const at = stageOf(vendors, one.stage, "median_s");
        const line = monitors.find((monitor) => monitor.metric === one.monitor && monitor.above && (monitor.agent === null || monitor.agent === agent));
        const state = at === null ? null : standing(at.seconds, line);
        return (
          <div key={one.stage} className="obs-provider">
            <span className="obs-provider-stage">{one.name}</span>
            <span className="obs-provider-who">
              <span className="obs-provider-name">{at === null ? "—" : [at.vendor, at.model].filter((word) => word !== null).join(" · ")}</span>
              {at !== null && <span className="obs-provider-key">{own.includes(at.vendor) ? "your key" : "lent by the runtime"}</span>}
            </span>
            <span className="obs-provider-took">{at === null ? "—" : took(at.seconds)}</span>
            <span className={state === "Slow" ? "obs-provider-state obs-tone-amber" : "obs-provider-state obs-tone-green"}>
              {state !== null && (
                <>
                  <span className={state === "Slow" ? "obs-dot-tone obs-tone-bg-amber" : "obs-dot-tone obs-tone-bg-green"} aria-hidden />
                  {state}
                </>
              )}
            </span>
          </div>
        );
      })}
    </Card>
  );
}
