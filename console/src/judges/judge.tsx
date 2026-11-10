/** One judge open beside the list: who it is and whether it is active, how it has done in a line of facts, then what it asks and a try on real calls. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { More } from "../apps/apps";
import { ConfirmButton } from "../apps/confirm";
import { ago, percent } from "../lib/format";
import { answersOf, readsOf, toneOf, whenOf, whoseOf } from "../quality/rules";
import { Badge, Toggle } from "../ui/setting";
import { Creature } from "./creature";
import type { Calibration, JudgeRow } from "./door";
import { isOurs, isSwitched, type Held } from "./fold";
import { TryJudge } from "./try";

// A question longer than this opens folded: it is a prompt, read when wanted and not before anything else.
const LONG = 320;

function Fact({ name, tone, under, children }: { name: string; tone?: string | undefined; under?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <div>
      <dt>{name}</dt>
      <dd className={tone === undefined ? undefined : `ql-tone-${tone}`}>{children}</dd>
      {under !== undefined && <dd className="jd-fact-under">{under}</dd>}
    </div>
  );
}

export function JudgeActions({ onEdit, onDrop }: { onEdit: () => void; onDrop: () => void }): ReactNode {
  return (
    <div className="app-actions">
      <button type="button" className="app-button" onClick={onEdit}>
        Edit
      </button>
      <More>
        <ConfirmButton label="Delete" asks="Delete this judge?" danger onConfirm={onDrop} />
      </More>
    </div>
  );
}

function Question({ text }: { text: string }): ReactNode {
  const [whole, setWhole] = useState(false);
  const long = text.length > LONG;
  return (
    <div className="jd-part">
      <h3 className="dash-eyebrow">What it asks</h3>
      <p className={long && !whole ? "jd-question jd-question-folded" : "jd-question"}>{text}</p>
      {long && (
        <button type="button" className="jd-whole" onClick={() => setWhole(!whole)}>
          {whole ? "Show less" : "Read it whole"}
        </button>
      )}
    </div>
  );
}

export function JudgeView({ judge, agent, held, read, agreement, busy, onSwitch }: { judge: JudgeRow; /** The agent in view, or "" for the org. */ agent: string; held: Held | undefined; /** How many judged calls the rate is over. */ read: number; agreement: Calibration | null; busy: boolean; onSwitch: (on: boolean) => void }): ReactNode {
  const share = held === undefined || held.settled === 0 ? null : held.held / held.settled;
  const broke = held === undefined ? 0 : held.settled - held.held;
  const reads = readsOf(judge);
  const agreed = agreement?.judges.find((one) => one.judge === judge.name);
  const about = judge.why ?? judge.summary ?? null;
  const inQuality = `/quality?judge=${encodeURIComponent(judge.name)}${agent === "" ? "" : `&agent=${encodeURIComponent(agent)}`}`;
  const switched = isSwitched(judge);
  const state = `${judge.on ? "Active" : "Off"}${switched ? (agent === "" ? " on every agent" : ` on ${agent}`) : ""}`;
  const left = agreement === null || agreed === undefined ? 0 : Math.max(0, agreement.labels_to_judge - agreed.compared);
  const verdict = agreed?.trusted === null ? `${left} more to tell` : agreed?.trusted === true ? "Trusted" : `Under the ${agreement === null ? "" : `${percent(agreement.agrees_at_least)} `}line`;

  return (
    <div className="jd-view">
      <section className="jd-hero" aria-label={judge.name}>
        <div className="jd-hero-top">
          <Creature name={judge.name} size={40} />
          <div className="jd-hero-words">
            <h2 className="jd-hero-title">
              <span className="dash-clip">{judge.name}</span>
              {isOurs(judge, agent) && <Badge>Yours</Badge>}
              {judge.owner === "class" && <Badge quiet>In code</Badge>}
              {agreed?.trusted === false && <span className="jd-untrusted">Untrusted</span>}
            </h2>
            {about !== null && <p className="dash-quiet jd-hero-about">{about}</p>}
            {judge.fixed === true && <p className="dash-quiet jd-hero-about">Its class declares it, so it is changed in the agent's code and read here.</p>}
          </div>
          <div className="jd-hero-state" title={switched ? (agent === "" ? "An agent may still switch it for itself." : "This agent's switch wins over the org's.") : undefined}>
            <span className={judge.on ? "jd-state-on" : "dash-quiet"}>{state}</span>
            {switched && <Toggle on={judge.on} label={`${judge.name} active`} disabled={busy} onChange={onSwitch} />}
          </div>
        </div>
        <dl className="jd-facts">
          <Fact
            name="Held"
            tone={share === null ? undefined : toneOf(share)}
            under={
              share === null ? (
                judge.on ? `None of the newest ${read} judged calls` : "Not asked while off"
              ) : broke > 0 ? (
                <Link to={inQuality} className="jd-fact-link">
                  Broke on {broke} of {held?.settled}
                </Link>
              ) : (
                `On all ${held?.settled}`
              )
            }
          >
            {share === null ? "—" : percent(share)}
          </Fact>
          <Fact name="Agrees with people" tone={agreed?.trusted === false ? "bad" : undefined} under={agreed === undefined || agreed.rate === null ? <span title={'Dismissing a case as "the judge was wrong" is a label, and so is approving one.'}>Nobody has labelled it</span> : `${agreed.agreed} of ${agreed.compared} labelled · ${verdict}`}>
            {agreed === undefined || agreed.rate === null ? "—" : percent(agreed.rate)}
          </Fact>
          <Fact name="Answers">{answersOf(judge)}</Fact>
          <Fact name="Runs on">{whenOf(judge)}</Fact>
          <Fact name="Also reads">
            <span className="dash-first">{reads === "" ? "Nothing but the call" : reads}</span>
          </Fact>
          <Fact name="Whose" under={judge.set_at == null ? undefined : `Written ${ago(judge.set_at)}`}>
            {whoseOf(judge)}
            {judge.version != null && ` · v${judge.version}`}
          </Fact>
        </dl>
      </section>

      <section className="dash-card" aria-label="What it asks">
        <Question text={judge.question} />
      </section>

      <section className="dash-card" aria-label="Try it on real calls">
        <div className="jd-part">
          <h3 className="dash-eyebrow">Try it on real calls</h3>
          <TryJudge agent={agent} name={judge.name} written={null} />
        </div>
      </section>
    </div>
  );
}
