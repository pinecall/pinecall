/** Advanced: when the agent starts and stops speaking, what it does when nobody talks or a machine answers, who takes over when a vendor fails, how a call runs, and what the organization sets for all its agents. One Save, so one change is one version. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { cornerOf, READ_ONLY } from "../configure/corner";
import { EditDialog } from "../configure/dialog";
import { readReport, readSettings, setSettings, type Report, type TuningAnswer, type TuningBody } from "../configure/door";
import { Locked, Pencil } from "../configure/stages";
import { Select } from "../ui/select";
import { Field, Setting, Slider, Toggle } from "../ui/setting";
import { readPolicy, readRunsOn, readWebhook, type Policy, type Webhook } from "./door";
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

type Part = "start" | "stop" | "quiet" | "voicemail" | "fallbacks" | "call";

// Each card, and the fields a class may declare in it: a card with none left open has nothing to edit.
const PARTS: readonly { part: Part; title: string; about: string; fields: readonly string[] }[] = [
  { part: "start", title: "When it starts speaking", about: "How the agent decides the caller has finished.", fields: ["stt", "turn"] },
  { part: "stop", title: "When it stops speaking", about: "Words that only agree, like “okay” or “sí”, never stop it. A noise that brings no words lets it carry on from where it paused.", fields: ["turn"] },
  { part: "quiet", title: "When nobody talks", about: "Only counts while the agent is waiting on the caller, never while it speaks, a tool runs or a person has the line.", fields: ["silence_timeout_s", "idle"] },
  { part: "voicemail", title: "Voicemail", about: "On calls the agent places. The model decides from what it hears, so a person is never treated as a machine by a tone.", fields: ["voicemail"] },
  { part: "fallbacks", title: "Fallbacks", about: "Who takes over, in order, when the vendor a call runs on fails. Each speaks the voice Pinecall has for the language. Set here, they replace Pinecall's own.", fields: ["stt_fallbacks", "tts_fallbacks"] },
  { part: "call", title: "The call", about: "How long it may run, and what is kept of it.", fields: ["max_duration_s", "record", "llm_timeout_s"] },
];

function Section({ title, about, onEdit, children }: { title: string; about: string; onEdit?: (() => void) | undefined; children: ReactNode }): ReactNode {
  return (
    <section className="dash-card" aria-label={title}>
      <div className="adv-head">
        <div className="adv-head-top">
          <h3 className="cfg-title">{title}</h3>
          {onEdit !== undefined && <Pencil label={`Change ${title.toLowerCase()}`} onClick={onEdit} />}
        </div>
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
  const [editing, setEditing] = useState<Part | null>(null);

  // An app shows what its calls run on, its class under the settings; what its class leaves open edits in the panel.
  const [runsOn, setRunsOn] = useState<TuningBody | null>(null);

  const load = useCallback(async (): Promise<void> => {
    const [settings, ran] = await Promise.all([readSettings(credentials, agent), kind === "code" ? readRunsOn(credentials, agent) : Promise.resolve(null)]);
    setAnswer(settings);
    setRunsOn(ran);
    setDraft(draftOf(ran ?? cornerOf(settings, false).inEffect?.config ?? {}));
  }, [credentials, agent, kind]);

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
  const own: TuningBody = corner.inEffect?.config ?? {};
  const fixed = new Set(answer.fixed);
  const was = draftOf(runsOn ?? own);
  const dirty = JSON.stringify(draft) !== JSON.stringify(was);
  const put = (changed: Partial<Draft>): void => setDraft({ ...draft, ...changed });
  const noLimit = draft.minutes === NO_LIMIT;
  const timing = draft.silenceTimeout !== "";
  // An app's page reads; each of its cards opens in the panel, where what its class left open edits.
  const paged = kind === "code";
  const mark = (name: string): ReactNode => (fixed.has(name) ? <Locked /> : undefined);

  const leave = (): void => {
    setEditing(null);
    setRefused(null);
    setDraft(was);
  };

  // Only what moved here moves: an app's view holds its class's values, which are never settings of its own.
  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      const moved = Object.fromEntries(Object.entries(draft).filter(([name, value]) => JSON.stringify(value) !== JSON.stringify(was[name as keyof Draft])));
      const base = draftOf(own);
      await setSettings(credentials, agent, { config: bodyOf(own, { ...base, ...moved }, base), if_version: corner.standing?.version ?? null, note: null, team: false });
      setEditing(null);
      await load();
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  const part = (which: Part, readOnly: boolean): ReactNode => {
    const off = (name: string): boolean => readOnly || fixed.has(name);
    switch (which) {
      case "start":
        return (
          <div className="adv-grid">
            <Setting icon="ear" title="Who ends the turn" about="What decides the caller is done talking." aside={mark("stt")}>
              <Select items={END_OF_TURN} value={draft.endOfTurn} label="Who ends the turn" disabled={off("stt")} onChange={(endOfTurn) => put({ endOfTurn })} />
            </Setting>
            <Setting icon="clock" title="Silence before it answers" about={`Milliseconds of quiet before the turn may end. ${SILENCE_MS} unless set.`} aside={mark("turn")}>
              <Slider value={draft.silenceMs} label="Silence before it answers" min={0} max={3000} step={50} rest={SILENCE_MS} ends={["Sooner", "Later"]} disabled={off("turn")} onChange={(silenceMs) => put({ silenceMs })} />
            </Setting>
            <Setting icon="gauge" title="End of turn confidence" about="How sure the transcriber must be that the turn is over. Deepgram Flux only." aside={mark("turn")}>
              <Slider value={draft.eot} label="End of turn confidence" min={0.5} max={0.9} step={0.05} rest={0.7} disabled={off("turn")} onChange={(eot) => put({ eot })} />
            </Setting>
            <Setting icon="bolt" title="Early guess confidence" about="How sure it must be to guess early that the turn is over. Never above the one before. Deepgram Flux only." aside={mark("turn")}>
              <Slider value={draft.eager} label="Early guess confidence" min={0.3} max={0.9} step={0.05} rest={0.5} disabled={off("turn")} onChange={(eager) => put({ eager })} />
            </Setting>
          </div>
        );
      case "stop":
        return (
          <div className="adv-grid">
            <Setting icon="type" title="Words to interrupt it" about={`How many words the caller says before the agent stops. ${WORDS_TO_INTERRUPT} unless set.`} aside={mark("turn")}>
              <Slider value={draft.words} label="Words to interrupt it" min={0} max={10} step={1} rest={WORDS_TO_INTERRUPT} disabled={off("turn")} onChange={(words) => put({ words })} />
            </Setting>
            <Setting icon="clock" title="Speech to interrupt it" about={`Milliseconds the caller must speak over the agent before it stops. ${INTERRUPT_MS} unless set.`} aside={mark("turn")}>
              <Slider value={draft.interruptMs} label="Speech to interrupt it" min={0} max={2000} step={50} rest={INTERRUPT_MS} disabled={off("turn")} onChange={(interruptMs) => put({ interruptMs })} />
            </Setting>
          </div>
        );
      case "quiet":
        return (
          <div className="adv-grid">
            <Setting icon="clock" title="Silence timeout" about={timing ? "Seconds of the caller saying nothing before the call ends." : "Off: silence alone never ends the call."} aside={mark("silence_timeout_s") ?? <Toggle on={timing} label="End the call after a silence" disabled={readOnly} onChange={(on) => put({ silenceTimeout: on ? SILENCE_TIMEOUT_S : "" })} />}>
              {timing && <Slider value={draft.silenceTimeout} label="Silence timeout, in seconds" min={5} max={3600} step={5} rest={30} ends={["5 s", "1 h"]} disabled={off("silence_timeout_s")} onChange={(silenceTimeout) => put({ silenceTimeout })} />}
            </Setting>
            <Setting icon="speaker" title="Idle messages" about="What it says, in turn, when the caller has gone quiet. One per line. None set: it says nothing." aside={mark("idle")}>
              <div className="adv-stack">
                <textarea className="cfg-input cfg-area" rows={3} aria-label="Idle messages" placeholder={"Are you still there?\nI'm here whenever you're ready."} value={draft.idleLines} readOnly={off("idle")} onChange={(event) => put({ idleLines: event.target.value })} />
                {draft.idleLines.trim() !== "" && (
                  <>
                    <Field label="Seconds before each one">
                      <Slider value={draft.idleAfter} label="Seconds before each idle message" min={5} max={60} step={0.5} rest={IDLE_AFTER_S} disabled={off("idle")} onChange={(idleAfter) => put({ idleAfter })} />
                    </Field>
                    <Field label="At most, until the caller speaks">
                      <Slider value={draft.idleTimes} label="Most idle messages" min={1} max={10} step={1} rest={IDLE_TIMES} disabled={off("idle")} onChange={(idleTimes) => put({ idleTimes })} />
                    </Field>
                  </>
                )}
              </div>
            </Setting>
          </div>
        );
      case "voicemail":
        return (
          <div className="adv-grid">
            <Setting icon="numbers" title="Detect voicemail" about={draft.voicemail ? "When a machine answers, it leaves the message below and hangs up. With no message it just hangs up." : "Off: it talks to whatever answers."} aside={mark("voicemail") ?? <Toggle on={draft.voicemail} label="Detect voicemail" disabled={readOnly} onChange={(voicemail) => put({ voicemail })} />}>
              {draft.voicemail && <textarea className="cfg-input cfg-area" rows={3} aria-label="Voicemail message" placeholder="Hi, this is the clinic. Please call us back when you can." value={draft.voicemailMessage} readOnly={off("voicemail")} onChange={(event) => put({ voicemailMessage: event.target.value })} />}
            </Setting>
          </div>
        );
      case "fallbacks":
        return report === null ? (
          <p className="dash-quiet">Reading the vendors…</p>
        ) : (
          <div className="adv-grid">
            <Setting icon="ear" title="Transcriber fallbacks" about="If the transcriber fails." aside={mark("stt_fallbacks")}>
              <Fallbacks label="Add a transcriber fallback" modality="stt" providers={report.providers} running={report.hears.vendor} value={draft.sttFallbacks} disabled={off("stt_fallbacks")} onChange={(sttFallbacks) => put({ sttFallbacks })} />
            </Setting>
            <Setting icon="speaker" title="Voice fallbacks" about="If the voice fails." aside={mark("tts_fallbacks")}>
              <Fallbacks label="Add a voice fallback" modality="tts" providers={report.providers} running={report.speaks.vendor} value={draft.ttsFallbacks} disabled={off("tts_fallbacks")} onChange={(ttsFallbacks) => put({ ttsFallbacks })} />
            </Setting>
          </div>
        );
      case "call":
        return (
          <div className="adv-grid">
            <Setting
              icon="clock"
              title="Longest call"
              about={noLimit ? "A voice call may run for as long as it lasts." : `Minutes a voice call may last. ${LONGEST_CALL_MIN} unless set.`}
              aside={mark("max_duration_s") ?? <Toggle on={!noLimit} label="Limit how long a call runs" disabled={readOnly} onChange={(on) => put({ minutes: on ? "" : NO_LIMIT })} />}
            >
              {!noLimit && <Slider value={draft.minutes} label="Longest call, in minutes" min={1} max={60} step={1} rest={LONGEST_CALL_MIN} ends={["1 min", "60 min"]} disabled={off("max_duration_s")} onChange={(minutes) => put({ minutes })} />}
            </Setting>
            <Setting icon="speaker" title="Keep the audio" about="Whether its calls keep their recording." aside={mark("record") ?? <Toggle on={draft.record} label="Keep the audio" disabled={readOnly} onChange={(record) => put({ record })} />} />
            <Setting icon="brain" title="Wait for the model" about={`Seconds a turn waits for the model's first word before it asks the caller to say it again. ${MODEL_WAIT_S} unless set.`} aside={mark("llm_timeout_s")}>
              <Slider value={draft.llmTimeout} label="Wait for the model, in seconds" min={1} max={60} step={1} rest={MODEL_WAIT_S} disabled={off("llm_timeout_s")} onChange={(llmTimeout) => put({ llmTimeout })} />
            </Setting>
          </div>
        );
    }
  };

  const open = PARTS.find((one) => one.part === editing);

  return (
    <div className="adv">
      {PARTS.map((one) => (
        <Section key={one.part} title={one.title} about={one.about} onEdit={paged && !READ_ONLY && one.fields.some((name) => !fixed.has(name)) ? () => setEditing(one.part) : undefined}>
          {part(one.part, READ_ONLY || paged)}
        </Section>
      ))}

      <Organization webhook={webhook} policy={policy} />

      {!paged && dirty && !READ_ONLY && (
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

      {open !== undefined && (
        <EditDialog title={open.title} about={open.about} saving={saving} refused={refused} onSave={() => void save()} onClose={leave}>
          {part(open.part, false)}
        </EditDialog>
      )}
    </div>
  );
}
