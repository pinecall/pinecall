/** Who is on the line right now: one card per live call, the one waiting for a person first and lifted, each a click from the call. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import type { ReactNode } from "react";

import { elapsed, wantsAPerson, whoOn } from "@pinecall/core/calls";
import { webVisitor } from "../../lib/format";
import { Avatar, ButtonLink } from "../../ui";

// More than this many at once is a floor, and Calls is where a floor is read.
const AT_MOST = 6;

export function OnTheLine({ live, agent }: { live: readonly SessionLine[]; agent: string }): ReactNode {
  const base = agent === "" ? "/calls" : `/a/${encodeURIComponent(agent)}/calls`;
  const shown = [...live].sort((a, b) => Number(wantsAPerson(b)) - Number(wantsAPerson(a))).slice(0, AT_MOST);
  if (shown.length === 0) {
    return <p className="ovw-quiet">Nobody is on the line. A call appears here the moment it rings.</p>;
  }
  return (
    <div className="ovw-live">
      {shown.map((line) => {
        const asking = wantsAPerson(line);
        return (
          <div key={line.call} className={asking ? "ovw-call ovw-call-asking" : "ovw-call"}>
            <div className="ovw-call-who">
              <Avatar name={whoOn(line, webVisitor)} size={28} round tint={asking ? "amber" : "green"} />
              <div className="ovw-call-words">
                <div className="ovw-call-name ui-clip">{whoOn(line, webVisitor)}</div>
                <div className="ovw-call-sub ui-clip">
                  {agent === "" && `${line.agent} · `}
                  {line.channel ?? "—"} · <span className="ovw-call-clock">{elapsed(line.started_at)}</span>
                </div>
              </div>
            </div>
            <div className={asking ? "ovw-call-said ovw-call-said-asking" : "ovw-call-said"}>
              {asking ? `Wants a person: ${line.attention?.reason ?? "the agent asked for one"}` : (line.outcome ?? "On a call now")}
            </div>
            <div className="ovw-call-moves">
              <ButtonLink to={`${base}/${line.call}`} size="xs" kind={asking ? "primary" : undefined}>
                {asking ? "Take the line" : "Listen"}
              </ButtonLink>
            </div>
          </div>
        );
      })}
    </div>
  );
}
