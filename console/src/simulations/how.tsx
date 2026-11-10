/** How a caller calls: typed, spoken or spoken over a room, for how many turns; and what that asks of the door. */

import type { ReactNode } from "react";

import { Icon, type IconName } from "../shell/icons";
import type { Ambience, Line, Wanted } from "./door";

const LINES: readonly { value: Line; icon: IconName; title: string; about: string }[] = [
  { value: "chat", icon: "chat", title: "Chat", about: "Typed. The fastest, and it uses no call minutes." },
  { value: "call", icon: "numbers", title: "Phone call", about: "Spoken out loud, on a clear line." },
  { value: "noisy", icon: "speaker", title: "Noisy call", about: "Spoken, with a room behind the caller the whole call." },
];

// "" is the caller's own room: what its persona says, a television when it says nothing.
const ROOMS: readonly { value: Ambience | ""; title: string; about: string }[] = [
  { value: "", title: "Caller's own", about: "What the caller is set to" },
  { value: "cafe", title: "Café", about: "Tables talking at once" },
  { value: "street", title: "Street", about: "Traffic, rising and fading" },
  { value: "office", title: "Office", about: "A steady hum" },
  { value: "television", title: "Television", about: "One voice competing" },
];

// The turns a caller improvises before it hangs up.
const LENGTHS: readonly { turns: number; name: string }[] = [
  { turns: 6, name: "Short" },
  { turns: 15, name: "Normal" },
  { turns: 30, name: "Long" },
];

// The room's level is dB under the caller's voice: fewer is louder. The slider reads the other way, as a volume does.
const FAINTEST_DB = 30;
const LOUDEST_DB = 5;

export interface How {
  line: Line;
  room: Ambience | "";
  db: number;
  /** Packets lost, percent. */
  loss: number;
  turns: number;
}

export const USUAL_HOW: How = { line: "call", room: "cafe", db: 15, loss: 0, turns: 15 };

/** What a call placed this way carries besides who rings whom. */
export function askedBy(how: How): Pick<Wanted, "voice" | "turns" | "interferer_db" | "packet_loss" | "ambience"> {
  const noise = how.line === "noisy" ? { interferer_db: how.db, packet_loss: how.loss / 100, ...(how.room === "" ? {} : { ambience: how.room }) } : {};
  return { voice: how.line !== "chat", turns: how.turns, ...noise };
}

function loudness(db: number): string {
  if (db <= 9) return "Loud";
  if (db <= 19) return "Clearly there";
  return "Faint";
}

export function HowTheyCall({ title, how, onChange }: { title: string; how: How; onChange: (how: How) => void }): ReactNode {
  const { line, room, db, loss, turns } = how;
  return (
    <section className="dash-card" aria-label={title}>
      <div className="dash-card-top">
        <span className="dash-eyebrow">{title}</span>
        <span className="sim-top-right">
          <span className="dash-quiet">Up to {turns} turns</span>
          <div className="dash-switch" role="group" aria-label="How long">
            {LENGTHS.map((one) => (
              <button key={one.turns} type="button" aria-pressed={turns === one.turns} className={turns === one.turns ? "dash-switch-on" : ""} onClick={() => onChange({ ...how, turns: one.turns })}>
                {one.name}
              </button>
            ))}
          </div>
        </span>
      </div>
      <div className="sim-ways" role="radiogroup" aria-label={title}>
        {LINES.map((one) => (
          <button key={one.value} type="button" role="radio" aria-checked={line === one.value} className={line === one.value ? "sim-way sim-way-on" : "sim-way"} onClick={() => onChange({ ...how, line: one.value })}>
            <span className="sim-way-icon">
              <Icon name={one.icon} size={16} />
            </span>
            <span className="sim-way-words">
              <span className="sim-way-title">{one.title}</span>
              <span className="sim-way-about">{one.about}</span>
            </span>
          </button>
        ))}
      </div>
      {line === "noisy" && (
        <div className="sim-noise">
          <div className="sim-rooms" role="radiogroup" aria-label="What plays behind the caller">
            {ROOMS.map((one) => (
              <button key={one.value} type="button" role="radio" aria-checked={room === one.value} className={room === one.value ? "sim-room sim-room-on" : "sim-room"} onClick={() => onChange({ ...how, room: one.value })}>
                <span className="sim-room-title">{one.title}</span>
                <span className="sim-room-about">{one.about}</span>
              </button>
            ))}
          </div>
          <label className="sim-level">
            <span className="sim-level-name">
              How loud
              <b>{loudness(db)}</b>
              <span className="dash-quiet">{db} dB under the voice</span>
            </span>
            <input type="range" aria-label="How loud the room is" min={0} max={FAINTEST_DB - LOUDEST_DB} step={1} value={FAINTEST_DB - db} onChange={(event) => onChange({ ...how, db: FAINTEST_DB - Number(event.target.value) })} />
          </label>
          <label className="sim-level">
            <span className="sim-level-name">
              Bad connection
              <b>{loss === 0 ? "None" : `${loss}% lost`}</b>
              <span className="dash-quiet">packets dropped off the line</span>
            </span>
            <input type="range" aria-label="Packets lost, percent" min={0} max={20} step={1} value={loss} onChange={(event) => onChange({ ...how, loss: Number(event.target.value) })} />
          </label>
        </div>
      )}
    </section>
  );
}
