/** Cards for the STT, LLM and TTS providers of a voice turn. */

import type { ReactNode } from "react";

import type { Stage } from "./door";

interface LegProps {
  stage: Stage;
  unavailable: string | null;
}

export function HearsLeg({ stage, unavailable }: LegProps): ReactNode {
  return (
    <Leg job="hears" stage={stage} unavailable={unavailable}>
      <Field label="Language" value={stage.language ?? "the vendor's default"} note="What the ear is told to expect; the runtime adds the names the state carries." />
      {stage.model !== null && stage.model !== "" && <Field label="Model" value={stage.model} />}
      <Field label="Switchable to" value="Any STT provider on file" note="Effective on the next session." />
    </Leg>
  );
}

export function DecidesLeg({ stage, unavailable }: LegProps): ReactNode {
  return (
    <Leg job="decides" stage={stage} unavailable={unavailable}>
      <Field label="Model" value={stage.model ?? "the vendor's default"} />
      <Field
        label="Prompt"
        value="identity · knowledge · tools · history · view"
        note="Named blocks in two regions, never reordered: the static ones are cached, the dynamic ones rewritten every turn."
      />
      <Field label="Tools" value="The class's @tool methods" />
    </Leg>
  );
}

export function SpeaksLeg({ stage, unavailable }: LegProps): ReactNode {
  return (
    <Leg job="speaks" stage={stage} unavailable={unavailable}>
      <Field label="Voice" value={stage.voice_id ?? "the vendor's default"} note="One of the voices this build curates, by name; the id is the vendor's." />
      {stage.model !== null && stage.model !== "" && <Field label="Model" value={stage.model} />}
      <Field label="Aligned transcript" value="On" note="Timed words, so the log knows when each word was spoken." />
    </Leg>
  );
}

function Leg({ job, stage, unavailable, children }: LegProps & { job: string; children: ReactNode }): ReactNode {
  return (
    <div className="ui-card">
      <div className="pipe-leg-head">
        <span className="pipe-leg-vendor">{stage.vendor}</span>
        <span className="pipe-leg-job">{job}</span>
      </div>
      <div className="pipe-leg-body">
        {children}
        {unavailable !== null && (
          <div className="pipe-field">
            <div className="pipe-label">Not right now</div>
            <div className="pipe-refused">{unavailable}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, note }: { label: string; value: string; note?: string }): ReactNode {
  return (
    <div className="pipe-field">
      <div className="pipe-label">{label}</div>
      <div className="pipe-value">{value}</div>
      {note !== undefined && <div className="pipe-note">{note}</div>}
    </div>
  );
}
