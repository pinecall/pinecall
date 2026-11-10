/** Live events: what the org's feed says as it happens, calls starting and ending, tools that ran or failed, a judge that said no, with no word of what was said. */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { feedOf } from "@pinecall/core/feed";
import type { Entry } from "@pinecall/core/wire/envelope";
import { Icon } from "../shell/icons";
import { took } from "./fold";

type Mood = "calm" | "good" | "warn" | "bad" | "accent";

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const timed = (value: unknown): string => (typeof value === "number" ? `, ${took(value)}` : "");

// What the feed says that is worth a line here, and how the line says it.
const SAYS: Readonly<Record<string, { said: string; mood: Mood; detail: (entry: Entry) => string }>> = {
  "call.started": { said: "Call started", mood: "good", detail: (entry) => [entry.agent, text(entry.data["channel"])].filter((word) => word !== "").join(", ") },
  "call.ended": { said: "Call ended", mood: "calm", detail: (entry) => text(entry.data["reason"]).replaceAll("_", " ") },
  "tool.ran": { said: "Tool ran", mood: "calm", detail: (entry) => `${text(entry.data["name"])}${timed(entry.data["duration_s"])}` },
  "tool.failed": { said: "Tool failed", mood: "bad", detail: (entry) => `${text(entry.data["name"])}${timed(entry.data["duration_s"])}` },
  "judge.broke": { said: "A judge said no", mood: "warn", detail: (entry) => text(entry.data["judge"]) },
  "attention.requested": { said: "Asked for a person", mood: "accent", detail: (entry) => entry.agent },
};

const KEEP = 40;
const SHOWN = 9;

/** Which of the lines a filter lets through. */
const FILTERS: readonly { name: string; lets: (entry: Entry) => boolean }[] = [
  { name: "All", lets: () => true },
  { name: "Problems", lets: (entry) => entry.type === "tool.failed" || entry.type === "judge.broke" },
  { name: "Tools", lets: (entry) => entry.type === "tool.ran" || entry.type === "tool.failed" },
];

const clockOf = (at: number): string => new Date(at * 1000).toLocaleTimeString("en-US", { hour12: false });

export function LiveEvents(): ReactNode {
  const credentials = useCredentials();
  const [events, setEvents] = useState<Entry[]>([]);
  const [filter, setFilter] = useState(0);
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

  const lets = FILTERS[filter]?.lets ?? (() => true);
  const shown = events.filter(lets).slice(0, SHOWN);

  return (
    <section className="dash-card ob-card" aria-label="Live events">
      <div className="dash-card-top ob-card-top">
        <span className="dash-eyebrow">
          <span className={paused ? "app-dot app-dot-calm" : "app-dot app-dot-good ob-live-dot"} aria-hidden="true" />
          Live events
        </span>
        <span className="ob-live-controls">
          <span className="dash-switch" role="group" aria-label="Which events">
            {FILTERS.map((one, at) => (
              <button key={one.name} type="button" aria-pressed={at === filter} className={at === filter ? "dash-switch-on" : ""} onClick={() => setFilter(at)}>
                {one.name}
              </button>
            ))}
          </span>
          <button type="button" className="sh-icon" aria-label={paused ? "Resume" : "Pause"} aria-pressed={paused} onClick={() => setPaused(!paused)}>
            <Icon name={paused ? "play" : "pause"} size={14} />
          </button>
        </span>
      </div>
      {shown.length === 0 ? (
        <p className="dash-empty">{paused ? "Paused." : "Waiting for the next event."}</p>
      ) : (
        <div className="dash-rows">
          {shown.map((entry) => {
            const says = SAYS[entry.type];
            const row = (
              <>
                <span className="ob-live-time">{clockOf(entry.ts)}</span>
                <span className={says?.mood === "calm" ? "ob-live-said" : says?.mood === "accent" ? "ob-live-said ob-live-accent" : `ob-live-said dash-mood-${says?.mood ?? "calm"}`}>{says?.said}</span>
                <span className="ob-live-detail ob-clip dash-quiet">{says?.detail(entry)}</span>
              </>
            );
            const key = `${entry.call ?? ""}-${entry.seq}-${entry.type}`;
            return entry.call === null ? (
              <div key={key} className="ob-row ob-live-row dash-row">
                {row}
              </div>
            ) : (
              <Link key={key} to={`/calls/${encodeURIComponent(entry.call)}`} className="ob-row ob-live-row dash-row">
                {row}
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
