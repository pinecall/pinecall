/** Advanced: when the agent starts and stops speaking, what it does when nobody talks or a machine answers, who takes over when a vendor fails, how a call runs, and what the organization sets for all its agents. One Save, so one change is one version. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { cornerOf, readOnlyFor } from "../configure/corner";
import { readReport, readSettings, setSettings, type Report, type TuningAnswer, type TuningBody } from "../configure/door";
import { Locked } from "../configure/stages";
import { Select } from "../ui/select";
import { Field, Setting, Slider, Toggle } from "../ui/setting";
import { readPolicy, readWebhook, type Policy, type Webhook } from "./door";
import { bodyOf, draftOf, type Draft } from "./draft";
import { Fallbacks } from "./fallbacks";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "./advanced.css";

// What the runtime does when a knob is left unset, where the slider rests.
const SILENCE_MS = 700;
const WORDS_TO_INTERRUPT = 2;
const INTERRUPT_MS = 500;
const IDLE_AFTER_S = 7.5;
const IDLE_TIMES = 3;
const LONGEST_CALL_MIN = 10;
const MODEL_WAIT_S = 12;
const NO_LIMIT = "0";
// Where a silence timeout starts when it is turned on.
const SILENCE_TIMEOUT_S = "30";

const END_OF_TURN = [
  { value: "", label: "Pinecall's default" },
  { value: "stt", label: "The transcriber", detail: "Only one that ends turns itself: Deepgram Flux" },
  { value: "smart-turn", label: "Smart Turn", detail: "A model that reads the end of the turn off the audio" },
  { value: "livekit", label: "LiveKit's detector", detail: "LiveKit's own end-of-turn model" },
];

function Section({ title, about, children }: { title: string; about: string; children: ReactNode }): ReactNode {
  return (
    <section className="dash-card" aria-label={title}>
      <div className="adv-head">
        <h3 className="cfg-title">{title}</h3>
        <p className="dash-quiet">{about}</p>
      </div>
      {children}
    </section>
  );
}

function OrgRow({ name, value }: { name: string; value: string }): ReactNode {
  return (
    <div className="cfg-row adv-org-row">
      <span className="cfg-row-name">{name}</span>
      <span className="cfg-row-value dash-clip" title={value}>
        {value}
      </span>
    </div>
  );
}

function Organization({ webhook, policy }: { webhook: Webhook | undefined; policy: Policy | undefined }): ReactNode {
  const unread = "Your role cannot read this";
  const hours = policy?.calling_hours;
  return (
    <Section title="For the whole organization" about="These apply to every agent of the organization, so they are not set agent by agent.">
      <div className="cfg-rows">
        <OrgRow name="Alerts webhook" value={webhook === undefined ? unread : webhook === null ? "None: alerts stay in the console" : `${webhook.url}${webhook.signed ? ", signed" : ""}`} />
        <OrgRow name="Calls kept for" value={policy === undefined ? unread : policy.retention_days == null ? "Default" : `${policy.retention_days} days`} />
        <OrgRow name="Recording notice" value={policy === undefined ? unread : policy.recording_notice ? "On" : "Off"} />
        <OrgRow name="Outbound consent" value={policy === undefined ? unread : policy.consent_everywhere ? "Required in every country" : "Required for US numbers"} />
        <OrgRow name="Calling hours" value={policy === undefined ? unread : hours == null ? "Any hour" : `${hours.from}:00 to ${hours.until}:00`} />
      </div>
    </Section>
  );
}

export function AdvancedTab({ agent, kind }: { agent: string; kind: "code" | "studio" }): ReactNode {
  const credentials = useCredentials();
  const [answer, setAnswer] = useState<TuningAnswer | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [webhook, setWebhook] = useState<Webhook | undefined>(undefined);
  const [policy, setPolicy] = useState<Policy | undefined>(undefined);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [away, setAway] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    const settings = await readSettings(credentials, agent);
    setAnswer(settings);
    setDraft(draftOf(cornerOf(settings, false).inEffect?.config ?? {}));
  }, [credentials, agent]);

  useEffect(() => {
    load().catch((failed: unknown) => setAway(saidBy(failed)));
    readReport(credentials, agent).then(setReport, () => undefined);
    // A key that may not read these still sees the agent's own settings.
    readWebhook(credentials).then(setWebhook, () => undefined);
    readPolicy(credentials).then(setPolicy, () => undefined);
  }, [credentials, agent, load]);

  if (away !== null) return <p className="cfg-refused">{away}</p>;
  if (answer === null || draft === null) return <p className="dash-quiet">Reading how it is set…</p>;

  const corner = cornerOf(answer, false);
  const config: TuningBody = corner.inEffect?.config ?? {};
  const fixed = new Set(answer.fixed);
  const readOnly = readOnlyFor(kind);
  const was = draftOf(config);
  const dirty = JSON.stringify(draft) !== JSON.stringify(was);
  const put = (changed: Partial<Draft>): void => setDraft({ ...draft, ...changed });
  const turnLocked = readOnly || fixed.has("turn");
  const turnMark = fixed.has("turn") ? <Locked /> : undefined;
  const noLimit = draft.minutes === NO_LIMIT;
  const timing = draft.silenceTimeout !== "";

  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      await setSettings(credentials, agent, { config: bodyOf(config, draft, was), if_version: corner.standing?.version ?? null, note: null, team: false });
      await load();
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="adv">
      <Section title="When it starts speaking" about="How the agent decides the caller has finished.">
        <div className="adv-grid">
          <Setting icon="ear" title="Who ends the turn" about="What decides the caller is done talking." aside={fixed.has("stt") ? <Locked /> : undefined}>
            <Select items={END_OF_TURN} value={draft.endOfTurn} label="Who ends the turn" disabled={readOnly || fixed.has("stt")} onChange={(endOfTurn) => put({ endOfTurn })} />
          </Setting>
          <Setting icon="clock" title="Silence before it answers" about={`Milliseconds of quiet before the turn may end. ${SILENCE_MS} unless set.`} aside={turnMark}>
            <Slider value={draft.silenceMs} label="Silence before it answers" min={0} max={3000} step={50} rest={SILENCE_MS} ends={["Sooner", "Later"]} disabled={turnLocked} onChange={(silenceMs) => put({ silenceMs })} />
          </Setting>
          <Setting icon="gauge" title="End of turn confidence" about="How sure the transcriber must be that the turn is over. Deepgram Flux only.">
            <Slider value={draft.eot} label="End of turn confidence" min={0.5} max={0.9} step={0.05} rest={0.7} disabled={turnLocked} onChange={(eot) => put({ eot })} />
          </Setting>
          <Setting icon="bolt" title="Early guess confidence" about="How sure it must be to guess early that the turn is over. Never above the one before. Deepgram Flux only.">
            <Slider value={draft.eager} label="Early guess confidence" min={0.3} max={0.9} step={0.05} rest={0.5} disabled={turnLocked} onChange={(eager) => put({ eager })} />
          </Setting>
        </div>
      </Section>

      <Section title="When it stops speaking" about="Words that only agree, like “okay” or “sí”, never stop it. A noise that brings no words lets it carry on from where it paused.">
        <div className="adv-grid">
          <Setting icon="type" title="Words to interrupt it" about={`How many words the caller says before the agent stops. ${WORDS_TO_INTERRUPT} unless set.`} aside={turnMark}>
            <Slider value={draft.words} label="Words to interrupt it" min={0} max={10} step={1} rest={WORDS_TO_INTERRUPT} disabled={turnLocked} onChange={(words) => put({ words })} />
          </Setting>
          <Setting icon="clock" title="Speech to interrupt it" about={`Milliseconds the caller must speak over the agent before it stops. ${INTERRUPT_MS} unless set.`} aside={turnMark}>
            <Slider value={draft.interruptMs} label="Speech to interrupt it" min={0} max={2000} step={50} rest={INTERRUPT_MS} disabled={turnLocked} onChange={(interruptMs) => put({ interruptMs })} />
          </Setting>
        </div>
      </Section>

      <Section title="When nobody talks" about="Only counts while the agent is waiting on the caller, never while it speaks, a tool runs or a person has the line.">
        <div className="adv-grid">
          <Setting icon="clock" title="Silence timeout" about={timing ? "Seconds of the caller saying nothing before the call ends." : "Off: silence alone never ends the call."} aside={<Toggle on={timing} label="End the call after a silence" disabled={readOnly} onChange={(on) => put({ silenceTimeout: on ? SILENCE_TIMEOUT_S : "" })} />}>
            {timing && <Slider value={draft.silenceTimeout} label="Silence timeout, in seconds" min={5} max={3600} step={5} rest={30} ends={["5 s", "1 h"]} disabled={readOnly} onChange={(silenceTimeout) => put({ silenceTimeout })} />}
          </Setting>
          <Setting icon="speaker" title="Idle messages" about="What it says, in turn, when the caller has gone quiet. One per line. None set: it says nothing.">
            <div className="adv-stack">
              <textarea className="cfg-input cfg-area" rows={3} aria-label="Idle messages" placeholder={"Are you still there?\nI'm here whenever you're ready."} value={draft.idleLines} readOnly={readOnly} onChange={(event) => put({ idleLines: event.target.value })} />
              {draft.idleLines.trim() !== "" && (
                <>
                  <Field label="Seconds before each one">
                    <Slider value={draft.idleAfter} label="Seconds before each idle message" min={5} max={60} step={0.5} rest={IDLE_AFTER_S} disabled={readOnly} onChange={(idleAfter) => put({ idleAfter })} />
                  </Field>
                  <Field label="At most, until the caller speaks">
                    <Slider value={draft.idleTimes} label="Most idle messages" min={1} max={10} step={1} rest={IDLE_TIMES} disabled={readOnly} onChange={(idleTimes) => put({ idleTimes })} />
                  </Field>
                </>
              )}
            </div>
          </Setting>
        </div>
      </Section>

      <Section title="Voicemail" about="On calls the agent places. The model decides from what it hears, so a person is never treated as a machine by a tone.">
        <div className="adv-grid">
          <Setting icon="numbers" title="Detect voicemail" about={draft.voicemail ? "When a machine answers, it leaves the message below and hangs up. With no message it just hangs up." : "Off: it talks to whatever answers."} aside={<Toggle on={draft.voicemail} label="Detect voicemail" disabled={readOnly} onChange={(voicemail) => put({ voicemail })} />}>
            {draft.voicemail && <textarea className="cfg-input cfg-area" rows={3} aria-label="Voicemail message" placeholder="Hi, this is the clinic. Please call us back when you can." value={draft.voicemailMessage} readOnly={readOnly} onChange={(event) => put({ voicemailMessage: event.target.value })} />}
          </Setting>
        </div>
      </Section>

      <Section title="Fallbacks" about="Who takes over, in order, when the vendor a call runs on fails. Each speaks the voice Pinecall has for the language. Set here, they replace Pinecall's own.">
        {report === null ? (
          <p className="dash-quiet">Reading the vendors…</p>
        ) : (
          <div className="adv-grid">
            <Setting icon="ear" title="Transcriber fallbacks" about="If the transcriber fails." aside={fixed.has("stt") ? <Locked /> : undefined}>
              <Fallbacks label="Add a transcriber fallback" modality="stt" providers={report.providers} running={report.hears.vendor} value={draft.sttFallbacks} disabled={readOnly} onChange={(sttFallbacks) => put({ sttFallbacks })} />
            </Setting>
            <Setting icon="speaker" title="Voice fallbacks" about="If the voice fails.">
              <Fallbacks label="Add a voice fallback" modality="tts" providers={report.providers} running={report.speaks.vendor} value={draft.ttsFallbacks} disabled={readOnly} onChange={(ttsFallbacks) => put({ ttsFallbacks })} />
            </Setting>
          </div>
        )}
      </Section>

      <Section title="The call" about="How long it may run, and what is kept of it.">
        <div className="adv-grid">
          <Setting
            icon="clock"
            title="Longest call"
            about={noLimit ? "A voice call may run for as long as it lasts." : `Minutes a voice call may last. ${LONGEST_CALL_MIN} unless set.`}
            aside={fixed.has("max_duration_s") ? <Locked /> : <Toggle on={!noLimit} label="Limit how long a call runs" disabled={readOnly} onChange={(on) => put({ minutes: on ? "" : NO_LIMIT })} />}
          >
            {!noLimit && <Slider value={draft.minutes} label="Longest call, in minutes" min={1} max={60} step={1} rest={LONGEST_CALL_MIN} ends={["1 min", "60 min"]} disabled={readOnly || fixed.has("max_duration_s")} onChange={(minutes) => put({ minutes })} />}
          </Setting>
          <Setting icon="speaker" title="Keep the audio" about="Whether its calls keep their recording." aside={fixed.has("record") ? <Locked /> : <Toggle on={draft.record} label="Keep the audio" disabled={readOnly} onChange={(record) => put({ record })} />} />
          <Setting icon="brain" title="Wait for the model" about={`Seconds a turn waits for the model's first word before it asks the caller to say it again. ${MODEL_WAIT_S} unless set.`} aside={fixed.has("llm_timeout_s") ? <Locked /> : undefined}>
            <Slider value={draft.llmTimeout} label="Wait for the model, in seconds" min={1} max={60} step={1} rest={MODEL_WAIT_S} disabled={readOnly || fixed.has("llm_timeout_s")} onChange={(llmTimeout) => put({ llmTimeout })} />
          </Setting>
        </div>
      </Section>

      <Organization webhook={webhook} policy={policy} />

      {dirty && !readOnly && (
        <div className="adv-bar" role="status">
          <span className={refused === null ? "dash-quiet adv-bar-said" : "cfg-refused adv-bar-said"}>{refused ?? "Unsaved changes. The next call runs on them once saved."}</span>
          <button type="button" className="app-button" disabled={saving} onClick={() => setDraft(was)}>
            Discard
          </button>
          <button type="button" className="cfg-save" disabled={saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      )}
    </div>
  );
}
