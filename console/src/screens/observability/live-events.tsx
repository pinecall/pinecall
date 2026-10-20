/** Live events: what the org's feed says as it happens — calls starting and ending, tools that ran or failed, a judge that said no — with no word of what was said. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { feedOf } from "@pinecall/core/feed";
import type { Entry } from "@pinecall/core/wire/envelope";
import { clockOf } from "../../lib/format";
import { Icon } from "../../ui";

// What the feed says that is worth a line here, and how a line says it: its name, its tone, and what it holds.
type Tone = "quiet" | "ink" | "tool" | "red" | "amber" | "violet";

const SAYS: Record<string, { tone: Tone; detail: (entry: Entry) => string }> = {
  "call.started": { tone: "ink", detail: (entry) => `${short(entry.call)} · ${entry.agent} · ${text(entry.data["channel"])}` },
  "call.ended": { tone: "quiet", detail: (entry) => `${short(entry.call)} · ${text(entry.data["reason"]).replace(/_/g, " ")}` },
  "tool.ran": { tone: "tool", detail: (entry) => `${short(entry.call)} · ${text(entry.data["name"])}${took(entry.data["duration_s"])} · ok` },
  "tool.failed": { tone: "red", detail: (entry) => `${short(entry.call)} · ${text(entry.data["name"])}${took(entry.data["duration_s"])} · failed` },
  "judge.broke": { tone: "amber", detail: (entry) => `${short(entry.call)} · ${text(entry.data["judge"])}` },
  "attention.requested": { tone: "violet", detail: (entry) => `${short(entry.call)} · ${entry.agent} · a caller asked for a person` },
};

const KEEP = 40;
const SHOWN = 9;

/** Which of the lines a chip lets through. */
const CHIPS = {
  All: () => true,
  Errors: (entry: Entry) => entry.type === "tool.failed" || entry.type === "judge.broke",
  Tools: (entry: Entry) => entry.type === "tool.ran" || entry.type === "tool.failed",
} as const;

function short(call: string | null): string {
  return call === null ? "" : call.slice(-9);
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function took(value: unknown): string {
  return typeof value === "number" ? ` · ${Math.round(value * 1000)} ms` : "";
}

export function LiveEvents(): ReactNode {
  const credentials = useCredentials();
  const [events, setEvents] = useState<Entry[]>([]);
  const [chip, setChip] = useState<keyof typeof CHIPS>("All");
  const [paused, setPaused] = useState(false);
  // The pause is read by the stream without opening it again.
  const stopped = useRef(false);
  stopped.current = paused;

  useEffect(
    () =>
      feedOf(credentials).listen({
        onEntry(entry) {
          if (stopped.current || SAYS[entry.type] === undefined) return;
          setEvents((was) => [entry, ...was].slice(0, KEEP));
        },
        onConnection: () => undefined,
      }),
    [credentials],
  );

  const shown = events.filter(CHIPS[chip]).slice(0, SHOWN);

  return (
    <div className="obs-live">
      <div className="obs-live-head">
        <span className="obs-live-title">
          <span className={paused ? "obs-dot-tone obs-tone-bg-quiet" : "obs-dot-tone obs-tone-bg-green"} aria-hidden />
          Live events
        </span>
        <span className="obs-chips" role="group" aria-label="Which events">
          {(Object.keys(CHIPS) as (keyof typeof CHIPS)[]).map((one) => (
            <button key={one} type="button" className={chip === one ? "obs-chip obs-chip-on" : "obs-chip"} onClick={() => setChip(one)}>
              {one}
            </button>
          ))}
        </span>
        <button type="button" className="obs-live-pause" title={paused ? "Resume" : "Pause"} aria-pressed={paused} onClick={() => setPaused(!paused)}>
          <Icon name={paused ? "play" : "stop"} size={13} />
        </button>
      </div>
      <div className="obs-live-list">
        {shown.length === 0 ? (
          <p className="obs-quiet obs-quiet-card">{paused ? "Paused." : "Waiting for the next event."}</p>
        ) : (
          shown.map((entry, index) => {
            const says = SAYS[entry.type];
            return (
              <div key={`${entry.ts}-${entry.type}-${entry.call ?? ""}-${index}`} className={index === 0 && !paused ? "obs-live-row obs-live-new" : "obs-live-row"}>
                <span className="obs-live-time">{clockOf(entry.ts)}</span>
                <span className={`obs-live-type obs-tone-${says?.tone ?? "quiet"}`}>{entry.type}</span>
                <span className="obs-live-detail">{says?.detail(entry)}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
