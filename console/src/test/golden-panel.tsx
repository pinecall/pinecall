/** A golden in the side panel: what the caller says and what must hold, how it stood the last time with the conversation it had, and the form that writes one. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useCall } from "@pinecall/core/use-call";
import { type Entry } from "@pinecall/core/wire/envelope";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { ago } from "../lib/format";
import { WORLD } from "../lib/world";
import { Field, Setting, Toggle } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { decideCase, dropCase, writeGolden, type EvalCase } from "./door";
import { A_NEW_GOLDEN, demandsOf, fitsTheForm, formOf, goldenOf, saidIn, turnsOf, type GoldenForm, type Result } from "./fold";
import { TurnsEditor } from "./golden-turns";

/** Where a golden came from, in a few words. */
export function fromOf(kept: EvalCase, authors: ReadonlyMap<string, string>): string {
  if (kept.source === "person") return `Written by ${authors.get(kept.author) ?? "a teammate"}`;
  return kept.source === "simulation" ? `Kept from a simulation${kept.persona ? ` of ${kept.persona}` : ""}` : "Kept from a real call";
}

type Heard = { id: string; who: "caller" | "agent"; text: string } | { id: string; who: "tool"; text: string; failed: boolean };

function heardOf(entry: Entry): Heard | null {
  const data = entry.data as Record<string, unknown>;
  if (entry.type === "turn.user" || entry.type === "turn.agent") {
    const text = typeof data["text"] === "string" ? data["text"].trim() : "";
    return text === "" ? null : { id: `t${entry.seq}`, who: entry.type === "turn.user" ? "caller" : "agent", text };
  }
  if (entry.type === "tool.result") return { id: `x${entry.seq}`, who: "tool", text: String(data["name"]), failed: data["error"] !== undefined && data["error"] !== null };
  return null;
}

/** The conversation a golden had the last time it was played, read from that call's log. */
function Conversation({ call }: { call: string }): ReactNode {
  const [heard, setHeard] = useState<Heard[]>([]);
  const { error, connection } = useCall(call, {
    onEntry(entry) {
      const line = heardOf(entry);
      if (line !== null) setHeard((was) => (was.some((one) => one.id === line.id) ? was : [...was, line]));
    },
  });
  if (error !== null) return <p className="dash-quiet">That call's log could not be read.</p>;
  if (heard.length === 0) return <p className="dash-quiet">{connection === "connecting" ? "Reading the call…" : "Nothing was said on that call."}</p>;
  return (
    <div className="tst-heard">
      {heard.map((line) =>
        line.who === "tool" ? (
          <span key={line.id} className={line.failed ? "tst-heard-tool tst-heard-tool-bad" : "tst-heard-tool"}>
            {line.failed ? "✗" : "✓"} {line.text}
          </span>
        ) : (
          <p key={line.id} className={line.who === "caller" ? "tst-heard-line tst-heard-caller" : "tst-heard-line"}>
            {line.text}
          </p>
        ),
      )}
    </div>
  );
}

function Script({ lines }: { lines: readonly string[] }): ReactNode {
  return (
    <ol className="tst-script">
      {lines.map((line, at) => (
        <li key={at}>{line}</li>
      ))}
    </ol>
  );
}

/** The golden as it is played: each line that goes in, and under it what must follow, in order. */
function Turns({ turns }: { turns: ReturnType<typeof turnsOf> }): ReactNode {
  return (
    <ol className="tst-script">
      {turns.map((turn, at) => (
        <li key={at}>
          <span className="tst-script-turn">
            {turn.said}
            {turn.then.length > 0 && (
              <ul className="tst-demands">
                {turn.then.map((step, which) => (
                  <li key={which} className={`tst-demand tst-demand-${step.tone}`}>
                    {step.text}
                  </li>
                ))}
              </ul>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

function LastTime({ result, playing }: { result: Result | undefined; playing: boolean }): ReactNode {
  if (playing) return <div className="tst-last tst-last-playing">Playing now…</div>;
  if (result === undefined) return <div className="tst-last">Never played. Run it to see how the agent takes it.</div>;
  return (
    <div className={`tst-last tst-last-${result.verdict}`}>
      <span className="tst-last-top">
        <b>{result.verdict === "held" ? "Held" : "Broke"}</b>
        <span className="dash-quiet">{ago(result.at)}</span>
      </span>
      {result.reasons.length > 0 && (
        <ul className="tst-reasons">
          {result.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One golden open. `kept` is null for one that lives in the app's code: the gateway knows only how it stood in a run. */
export function GoldenPanel({ name, kept, authors, result, playing, busy, onRun, onEdit, onChanged, onRemoved, onClose }: { name: string; kept: EvalCase | null; authors: ReadonlyMap<string, string>; result: Result | undefined; playing: boolean; /** A run is on: another waits for it. */ busy: boolean; onRun: () => void; onEdit: () => void; onChanged: (kept: EvalCase) => void; onRemoved: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [refused, setRefused] = useState<string | null>(null);
  const act = async (doing: () => Promise<void>): Promise<void> => {
    setRefused(null);
    try {
      await doing();
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };
  const demands = demandsOf(kept?.golden.expect);
  return (
    <SidePanel
      title={name}
      icon="goldens"
      about={kept === null ? "This golden lives in the app's code. It is edited there and played by pinecall test; here is how it stood in the last run." : `${fromOf(kept, authors)}, ${ago(kept.created_at)}.`}
      onClose={onClose}
      footer={
        kept !== null && (
          <>
            {refused !== null && <p className="cfg-refused">{refused}</p>}
            <div className="cfg-dialog-foot">
              <ConfirmButton label="Delete" asks="Delete this golden?" danger onConfirm={() => void act(async () => (await dropCase(credentials, kept.id), onRemoved()))} />
              {fitsTheForm(kept) && (
                <button type="button" className="app-button" onClick={onEdit}>
                  Edit
                </button>
              )}
              <button type="button" className="cfg-save" disabled={busy} onClick={onRun}>
                {playing ? "Playing…" : "Run"}
              </button>
            </div>
          </>
        )
      }
    >
      <LastTime result={result} playing={playing} />
      {kept !== null && (
        <>
          <Field label="Turn by turn">
            <Turns turns={turnsOf(kept.golden)} />
          </Field>
          <Field label="By the end of the conversation">
            {demands.length === 0 ? (
              <p className="dash-quiet">Nothing more is asked of the whole conversation.</p>
            ) : (
              <ul className="tst-demands">
                {demands.map((one) => (
                  <li key={one.text} className={`tst-demand tst-demand-${one.tone}`}>
                    {one.text}
                  </li>
                ))}
              </ul>
            )}
          </Field>
          <Setting icon="clock" title="Held out" about="Left out of Run and of the nightly run. It is played only when you run it by itself." aside={<Toggle on={kept.held_out} label="Held out" onChange={(on) => void act(async () => onChanged(await decideCase(credentials, kept.id, { held_out: on })))} />} />
        </>
      )}
      {result?.call != null && !playing && (
        <Field label="The last conversation">
          <Conversation key={result.call} call={result.call} />
        </Field>
      )}
    </SidePanel>
  );
}

/** A golden written, or one a person wrote changed. Its name is its address, so a golden already kept keeps its own. */
export function GoldenFormPanel({ agent, was, onSaved, onClose }: { agent: string; was: EvalCase | undefined; onSaved: (kept: EvalCase) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [form, setForm] = useState<GoldenForm>(() => (was === undefined ? A_NEW_GOLDEN : formOf(was)));
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const set = <Key extends keyof GoldenForm>(key: Key, value: GoldenForm[Key]): void => setForm((held) => ({ ...held, [key]: value }));

  const save = async (): Promise<void> => {
    const made = goldenOf(form, was?.golden);
    if ("refused" in made) return setRefused(made.refused);
    setSaving(true);
    setRefused(null);
    try {
      onSaved(await writeGolden(credentials, agent, made.golden.name, { golden: made.golden, held_out: form.heldOut }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EditDialog title={was === undefined ? "New golden" : `Edit ${was.name}`} icon="goldens" about="A conversation written down: what the caller says, and what the agent must do with it. Run plays it against the agent and says whether it held." saving={saving} refused={refused} onSave={() => void save()} onClose={onClose}>
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="never-quotes-a-price" spellCheck={false} value={form.name} disabled={was !== undefined} onChange={(event) => set("name", event.target.value)} />
      </Field>
      <Field label="Turn by turn">
        <span className="tst-hint">What the caller says, line by line. Under a line, what the agent must do right after it, in order. The first step that fails stops the golden there.</span>
        <TurnsEditor turns={form.turns} onChange={(turns) => set("turns", turns)} />
      </Field>
      <span className="tst-divide">By the end of the conversation</span>
      <Setting icon="check" title="The agent says" about="Words that must be in its replies, separated by commas.">
        <input className="cfg-input" aria-label="The agent says" placeholder="appointment, Tuesday" value={form.says} onChange={(event) => set("says", event.target.value)} />
      </Setting>
      <Setting icon="close" title="It never says" about="Words that must not be in any reply.">
        <input className="cfg-input" aria-label="It never says" placeholder="dollars, $" value={form.never} onChange={(event) => set("never", event.target.value)} />
      </Setting>
      <Setting icon="tools" title="It calls these tools" about="The tools the conversation must run, by name.">
        <input className="cfg-input" aria-label="It calls these tools" placeholder="book_appointment" spellCheck={false} value={form.tools} onChange={(event) => set("tools", event.target.value)} />
      </Setting>
      <Setting icon="tools" title="It never calls" about="The tools it must leave alone.">
        <input className="cfg-input" aria-label="It never calls" placeholder="cancel_appointment" spellCheck={false} value={form.neverTools} onChange={(event) => set("neverTools", event.target.value)} />
      </Setting>
      <Setting icon="knowledge" title="Answers from its knowledge" about="Every fact it gives must come from its documents or a tool." aside={<Toggle on={form.grounded} label="Answers from its knowledge" onChange={(on) => set("grounded", on)} />} />
      <Setting icon="clock" title="Held out" about="Left out of Run and of the nightly run." aside={<Toggle on={form.heldOut} label="Held out" onChange={(on) => set("heldOut", on)} />} />
    </EditDialog>
  );
}

/** A call a judge broke on, waiting for a person: what broke, what the caller said, and the decision. Approved, it is a golden. */
export function WaitingPanel({ kept, authors, onDecided, onClose }: { kept: EvalCase; authors: ReadonlyMap<string, string>; onDecided: (kept: EvalCase) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [deciding, setDeciding] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const decide = async (status: "approved" | "dismissed"): Promise<void> => {
    setDeciding(true);
    setRefused(null);
    try {
      onDecided(await decideCase(credentials, kept.id, { status }));
    } catch (failed) {
      setRefused(saidBy(failed));
      setDeciding(false);
    }
  };
  return (
    <SidePanel
      title={kept.name}
      icon="cases"
      about={`${fromOf(kept, authors)}, ${ago(kept.created_at)}. A judge broke on it. Keep it as a golden and every run plays it again, or dismiss it if the agent did nothing wrong.`}
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" disabled={deciding} onClick={() => void decide("dismissed")}>
              Dismiss
            </button>
            <button type="button" className="cfg-save" disabled={deciding} onClick={() => void decide("approved")}>
              Keep as a golden
            </button>
          </div>
        </>
      }
    >
      {kept.broke.length > 0 && (
        <div className="tst-last tst-last-broke">
          <ul className="tst-reasons">
            {kept.broke.map((one) => (
              <li key={one.judge}>
                <b>{one.judge}</b> {one.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Field label="The caller said">
        <Script lines={saidIn(kept.golden)} />
      </Field>
      {/* A call's log is read in the world it was made in. */}
      {kept.source_call !== null && kept.source_env === WORLD && (
        <Field label="The conversation">
          <Conversation key={kept.source_call} call={kept.source_call} />
        </Field>
      )}
    </SidePanel>
  );
}
