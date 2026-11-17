/** How a caller calls: typed, spoken in the agent's room or rung by phone, on a clear line or a bad one, for how many turns, with the agent's model of interruptions as it is set or its opposite; and what that asks of the door. */

import type { ReactNode } from "react";

import { Icon, type IconName } from "../shell/icons";
import type { Ambience, Wanted, Way } from "./door";

// How the caller reaches the agent. A phone call is a SIP leg in a carrier's codec, which only the sandbox dials.
const WAYS: readonly { value: Way; icon: IconName; title: string; about: string }[] = [
  { value: "chat", icon: "chat", title: "Chat", about: "Typed. The fastest, and it uses no call minutes." },
  { value: "web", icon: "wave", title: "Web call", about: "Spoken, in the agent's room, as a browser calls." },
  { value: "phone", icon: "numbers", title: "Phone call", about: "Spoken, rung over SIP in a carrier's codec, as a phone calls." },
];

// What a spoken call crosses on its way to the agent, whichever way it calls.
const LINES: readonly { bad: boolean; name: string }[] = [
  { bad: false, name: "Clear" },
  { bad: true, name: "Bad" },
];

// "" is the caller's own room: what its persona says, a television when it says nothing. "quiet" is no room at all.
const ROOMS: readonly { value: Room; title: string; about: string }[] = [
  { value: "quiet", title: "Quiet", about: "Nothing behind the caller" },
  { value: "", title: "Caller's own", about: "What the caller is set to" },
  { value: "cafe", title: "Café", about: "Tables talking at once" },
  { value: "street", title: "Street", about: "Traffic, rising and fading" },
  { value: "office", title: "Office", about: "A steady hum" },
  { value: "television", title: "Television", about: "A newscast across the room" },
];

// The turns a caller improvises before it hangs up.
const LENGTHS: readonly { turns: number; name: string }[] = [
  { turns: 6, name: "Short" },
  { turns: 15, name: "Normal" },
  { turns: 30, name: "Long" },
];

// The agent's small model for this call alone: the same caller with it and without.
const MODELS: readonly { knob: "interruptions"; title: string; about: string }[] = [
  { knob: "interruptions", title: "Smart interruptions", about: "the model that tells a real interruption from an “mm-hmm”" },
];
const CHOICES: readonly { value: Choice; name: string }[] = [
  { value: "own", name: "Agent's setting" },
  { value: "on", name: "On" },
  { value: "off", name: "Off" },
];

// The room's level is dB under the caller's voice: fewer is louder. The slider reads the other way, as a volume does.
const FAINTEST_DB = 30;
const LOUDEST_DB = 5;
// Past these a line is no line: nobody holds a conversation half a second apart each way.
const LONGEST_DELAY_MS = 600;
const MOST_JITTER_MS = 200;

/** The agent's own setting, or the model on or off for this call whatever the setting says. */
export type Choice = "own" | "on" | "off";

/** What plays behind the caller on a bad line: one of the rooms, the caller's own, or nothing. */
export type Room = Ambience | "" | "quiet";

export interface How {
  way: Way;
  /** A spoken call's line: clear, or one with a room behind the caller and a network that loses and holds its packets. */
  bad: boolean;
  room: Room;
  db: number;
  /** Packets lost, percent. */
  loss: number;
  /** Milliseconds the line holds every packet, and how far that moves from one to the next. */
  delay: number;
  jitter: number;
  turns: number;
  interruptions: Choice;
}

export const USUAL_HOW: How = { way: "web", bad: false, room: "cafe", db: 15, loss: 0, delay: 0, jitter: 0, turns: 15, interruptions: "own" };

/** What a call placed this way carries besides who rings whom. */
export function askedBy(how: How): Pick<Wanted, "voice" | "turns" | "interferer_db" | "packet_loss" | "ambience" | "via" | "delay_ms" | "jitter_ms" | "against"> {
  const spoken = how.way !== "chat";
  const bad = spoken && how.bad;
  const room = bad && how.room !== "quiet" ? { interferer_db: how.db, ...(how.room === "" ? {} : { ambience: how.room }) } : {};
  const network = bad ? { ...(how.loss > 0 ? { packet_loss: how.loss / 100 } : {}), ...(how.delay > 0 ? { delay_ms: how.delay } : {}), ...(how.jitter > 0 ? { jitter_ms: how.jitter } : {}) } : {};
  // Only a caller that rings is said: the agent's room is what the gateway does unasked.
  const via = how.way === "phone" ? { via: "sip" as const } : {};
  // Only a spoken call has audio for a model to hear, and only a choice that is not the agent's own is said.
  const against = !spoken || how.interruptions === "own" ? {} : { against: { smart_interruptions: how.interruptions === "on" } };
  return { voice: spoken, turns: how.turns, ...room, ...network, ...via, ...against };
}

function loudness(db: number): string {
  if (db <= 9) return "Loud";
  if (db <= 19) return "Clearly there";
  return "Faint";
}

/** `chooses` is whether this form may run a call with a model its agent is not set to: the sandbox's, one call at a time. `rings` is whether a caller may ring the agent by phone here: the sandbox's. */
export function HowTheyCall({ title, how, onChange, chooses = false, rings = false }: { title: string; how: How; onChange: (how: How) => void; chooses?: boolean; rings?: boolean }): ReactNode {
  const { way, bad, room, db, loss, delay, jitter, turns } = how;
  const ways = WAYS.filter((one) => rings || one.value !== "phone");
  const spoken = way !== "chat";
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
      <div className={ways.length === 2 ? "sim-ways sim-ways-two" : "sim-ways"} role="radiogroup" aria-label={title}>
        {ways.map((one) => (
          <button key={one.value} type="button" role="radio" aria-checked={way === one.value} className={way === one.value ? "sim-way sim-way-on" : "sim-way"} onClick={() => onChange({ ...how, way: one.value })}>
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
      {spoken && (
        <div className="sim-level sim-model">
          <span className="sim-level-name">
            The line
            <span className="dash-quiet">{bad ? "a room behind the caller, and a network that loses and holds its packets" : "nothing behind the caller, and every packet arrives"}</span>
          </span>
          <div className="dash-switch" role="group" aria-label="The line the caller is on">
            {LINES.map((one) => (
              <button key={one.name} type="button" aria-pressed={bad === one.bad} className={bad === one.bad ? "dash-switch-on" : ""} onClick={() => onChange({ ...how, bad: one.bad })}>
                {one.name}
              </button>
            ))}
          </div>
        </div>
      )}
      {spoken && bad && (
        <div className="sim-noise">
          <div className="sim-rooms" role="radiogroup" aria-label="What plays behind the caller">
            {ROOMS.map((one) => (
              <button key={one.value} type="button" role="radio" aria-checked={room === one.value} className={room === one.value ? "sim-room sim-room-on" : "sim-room"} onClick={() => onChange({ ...how, room: one.value })}>
                <span className="sim-room-title">{one.title}</span>
                <span className="sim-room-about">{one.about}</span>
              </button>
            ))}
          </div>
          {room !== "quiet" && (
            <label className="sim-level">
              <span className="sim-level-name">
                How loud
                <b>{loudness(db)}</b>
                <span className="dash-quiet">{db} dB under the voice</span>
              </span>
              <input type="range" aria-label="How loud the room is" min={0} max={FAINTEST_DB - LOUDEST_DB} step={1} value={FAINTEST_DB - db} onChange={(event) => onChange({ ...how, db: FAINTEST_DB - Number(event.target.value) })} />
            </label>
          )}
          <label className="sim-level">
            <span className="sim-level-name">
              Packets lost
              <b>{loss === 0 ? "None" : `${loss}%`}</b>
              <span className="dash-quiet">dropped off the line, each way</span>
            </span>
            <input type="range" aria-label="Packets lost, percent" min={0} max={20} step={1} value={loss} onChange={(event) => onChange({ ...how, loss: Number(event.target.value) })} />
          </label>
          <label className="sim-level">
            <span className="sim-level-name">
              Delay
              <b>{delay === 0 ? "None" : `${delay} ms`}</b>
              <span className="dash-quiet">every packet held, each way</span>
            </span>
            <input type="range" aria-label="Delay, milliseconds" min={0} max={LONGEST_DELAY_MS} step={10} value={delay} onChange={(event) => onChange({ ...how, delay: Number(event.target.value) })} />
          </label>
          <label className="sim-level">
            <span className="sim-level-name">
              Jitter
              <b>{jitter === 0 ? "None" : `± ${jitter} ms`}</b>
              <span className="dash-quiet">how far the delay moves from packet to packet</span>
            </span>
            <input type="range" aria-label="Jitter, milliseconds" min={0} max={MOST_JITTER_MS} step={5} value={jitter} onChange={(event) => onChange({ ...how, jitter: Number(event.target.value) })} />
          </label>
        </div>
      )}
      {chooses &&
        spoken &&
        MODELS.map((model) => (
          <div key={model.knob} className="sim-level sim-model">
            <span className="sim-level-name">
              {model.title}
              <span className="dash-quiet">{model.about}</span>
            </span>
            <div className="dash-switch" role="group" aria-label={`${model.title} for this call`}>
              {CHOICES.map((one) => (
                <button key={one.value} type="button" aria-pressed={how[model.knob] === one.value} className={how[model.knob] === one.value ? "dash-switch-on" : ""} onClick={() => onChange({ ...how, [model.knob]: one.value })}>
                  {one.name}
                </button>
              ))}
            </div>
          </div>
        ))}
    </section>
  );
}
