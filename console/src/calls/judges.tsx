/** Each judge in a line: what it answered, and when it broke why, with the lines it cites a click from the conversation. */

import type { ReactNode } from "react";

import { type Judgment } from "@pinecall/core/wire/events";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { Icon, type IconName } from "../shell/icons";

interface Look {
  icon: IconName;
  mood: "bad" | "good" | "accent" | "quiet";
  said?: string;
}

const VERDICT: Record<string, Look> = {
  broken: { icon: "close", mood: "bad", said: "Broke" },
  held: { icon: "check", mood: "good", said: "Held" },
  classified: { icon: "check", mood: "accent" },
};
const QUIET: Look = { icon: "more", mood: "quiet" };

function answerOf(judge: Judgment): string {
  if (judge.verdict === "classified") {
    if (judge.choice !== null && judge.choice !== undefined) return judge.choice;
    return judge.score === null || judge.score === undefined ? "Classified" : `${judge.score}/5`;
  }
  return judge.verdict === "na" ? "N/A" : judge.verdict;
}

function JudgeLine({ judge, onCite }: { judge: Judgment; onCite: (seq: number) => void }): ReactNode {
  const look = VERDICT[judge.verdict] ?? QUIET;
  const broke = judge.verdict === "broken";
  return (
    <div className="calls-judge" title={broke ? undefined : judge.reason}>
      <span className={`calls-judge-icon calls-mood-${look.mood}`}>
        <Icon name={look.icon} size={14} />
      </span>
      <span className="calls-judge-name dash-clip">{judge.name}</span>
      <span className={`calls-judge-said dash-first calls-mood-${look.mood}`}>{look.said ?? answerOf(judge)}</span>
      {broke && (
        <p className="calls-judge-why">
          {judge.reason}
          {judge.evidence.seqs.map((seq) => (
            <button key={seq} type="button" className="calls-cite" title="Go to this line" onClick={() => onCite(seq)}>
              #{seq}
            </button>
          ))}
        </p>
      )}
    </div>
  );
}

export function Judges({ score, onCite }: { score: CallScore | null; onCite: (seq: number) => void }): ReactNode {
  const judges = score?.judges ?? [];
  const broke = judges.filter((judge) => judge.verdict === "broken").length;
  const settled = judges.filter((judge) => judge.verdict === "held" || judge.verdict === "broken").length;
  // Judges on the panel that answered nothing are listed too, so coverage is never overstated.
  const silent = (score?.panel ?? []).filter((name) => !judges.some((judge) => judge.name === name));
  return (
    <section className="calls-part" aria-label="The judges">
      <div className="calls-part-top">
        <span className="dash-eyebrow">Judges</span>
        {settled > 0 && <span className="dash-quiet">{broke > 0 ? `${broke} of ${settled} broke` : `${settled} of ${settled} held`}</span>}
      </div>
      {score === null ? (
        <p className="dash-quiet">Not judged yet.</p>
      ) : judges.length === 0 && silent.length === 0 ? (
        <p className="dash-quiet">No judge was given to this call.</p>
      ) : (
        <div className="calls-judges">
          {judges.map((judge) => (
            <JudgeLine key={judge.name} judge={judge} onCite={onCite} />
          ))}
          {silent.map((name) => (
            <div key={name} className="calls-judge" title="It was run over this call and answered nothing.">
              <span className="calls-judge-icon calls-mood-quiet">
                <Icon name="more" size={14} />
              </span>
              <span className="calls-judge-name dash-clip">{name}</span>
              <span className="calls-judge-said calls-mood-quiet">No answer</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
