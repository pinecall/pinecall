/** Room panel: LiveKit participants, who is speaking, and the dialled number for phone calls. */

import { type Room } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import { Dot, SectionLabel } from "../../ui";

/** Participants as reported by the room; text sessions have none. */
export function RoomPanel({ room, from, over }: { room: Room | null; from: string | null; over: boolean }): ReactNode {
  return (
    <>
      <SectionLabel ruled>Room</SectionLabel>
      {room === null ? (
        <div className="call-pane-text">No room: this session carries no media.</div>
      ) : (
        <div className="call-pane-text">
          {over ? "Audio room closed" : "Audio room open"} · {room.participants.length}{" "}
          {room.participants.length === 1 ? "participant" : "participants"}
          {from !== null && <> · rang from {from}</>}
          <ul className="call-people">
            {room.participants.map((who) => (
              <li className="call-person" key={who.identity}>
                <details>
                  <summary>
                    <Dot tone={who.speaking ? "green" : undefined} small />
                    <span>{who.name ?? who.identity}</span>
                    <span className="call-person-kind">{who.kind}</span>
                  </summary>
                  {/* SIP trunk headers carry the phone number. */}
                  <pre className="call-data">{JSON.stringify(who.attributes, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
