/** Defaults: what a call runs on when neither its agent nor its settings chose: the three stages, the judge, the simulated caller, voices, rates, and the advanced row. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { EditDialog } from "../configure/dialog";
import { brandOf } from "../configure/vendors";
import { useMove } from "../numbers/parts";
import type { IconName } from "../shell/icons";
import { Field } from "../ui/setting";
import { readCatalogue, readHeldVendors, readProvidersRow, saveProvidersRow, STAGES, type ProvidersRow, type Stage, type StageName } from "./settings-door";
import { Effect, Refusal, Section, useDoor } from "./settings-parts";
import { DefaultRates } from "./settings-rates";
import { SpendPanel, StagePanel, stageSaid, type Known } from "./settings-stage";
import { DefaultVoices } from "./settings-voices";

const STAGE_ABOUT: Record<StageName, { name: string; icon: IconName; does: string; panel: string }> = {
  stt: { name: "Transcriber", icon: "ear", does: "Turns what the caller says into text.", panel: "What listens to the caller when an agent has not chosen." },
  llm: { name: "Model", icon: "brain", does: "Decides what the agent answers.", panel: "What thinks for an agent that has not chosen." },
  tts: { name: "Voice", icon: "speaker", does: "Speaks the agent's answer.", panel: "What speaks for an agent that has not chosen." },
};

type Open = { stage: StageName } | "judge" | "caller" | "hints" | "tuning" | null;

function HintsPanel({ hints, saving, refused, onSave, onClose }: { hints: readonly string[]; saving: boolean; refused: string | null; onSave: (hints: string[]) => void; onClose: () => void }): ReactNode {
  const [typed, setTyped] = useState(hints.join(", "));
  return (
    <EditDialog title="Languages also listened for" icon="ear" about="The languages a caller may speak besides the agent's own." saving={saving} refused={refused} onSave={() => onSave(typed.split(",").map((one) => one.trim()).filter((one) => one !== ""))} onClose={onClose}>
      <Effect>The transcriber of every call is told to expect these too, from the next call. Listing a language nobody speaks makes it mishear more.</Effect>
      <Field label="Language codes">
        <input className="cfg-input" aria-label="Language codes" placeholder="es, en, pt" spellCheck={false} value={typed} onChange={(event) => setTyped(event.target.value)} />
        <p className="dash-quiet">Separated by commas. Empty for none.</p>
      </Field>
    </EditDialog>
  );
}

function TuningPanel({ tuning, saving, refused, onSave, onClose }: { tuning: Record<string, unknown>; saving: boolean; refused: string | null; onSave: (tuning: Record<string, unknown>) => void; onClose: () => void }): ReactNode {
  const [typed, setTyped] = useState(() => JSON.stringify(tuning, null, 2));
  const [wrong, setWrong] = useState<string | null>(null);
  const save = (): void => {
    try {
      const parsed: unknown = JSON.parse(typed);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return setWrong("It must be one JSON object, keyed by stage and vendor.");
      setWrong(null);
      onSave(parsed as Record<string, unknown>);
    } catch {
      setWrong("This is not valid JSON. Nothing was saved.");
    }
  };
  return (
    <EditDialog title="Vendor tuning" icon="tools" about="What each vendor or model is told, in its own field names. For whoever knows the vendor's API." saving={saving} refused={wrong ?? refused} onSave={save} onClose={onClose}>
      <Effect>It changes how every call on these vendors behaves, from the next call: how a turn ends, what a model is asked. A wrong field can break calls for every organization.</Effect>
      <Field label="Tuning, as JSON">
        <textarea className="cfg-input cfg-area bxs-json" aria-label="Tuning, as JSON" rows={20} spellCheck={false} value={typed} onChange={(event) => setTyped(event.target.value)} />
        <p className="dash-quiet">A key is a stage and a vendor, like llm/anthropic, or a model after them. The longest match wins.</p>
      </Field>
    </EditDialog>
  );
}

export function SettingsDefaults(): ReactNode {
  const credentials = useCredentials();
  const door = useDoor(useCallback(() => readProvidersRow(credentials), [credentials]));
  const vendors = useDoor(useCallback(() => readHeldVendors(credentials), [credentials]));
  const catalogue = useDoor(useCallback(() => readCatalogue(credentials), [credentials]));
  const acting = useMove();
  const [open, setOpen] = useState<Open>(null);
  const close = useCallback(() => setOpen(null), []);
  const { reread } = door;
  // The row is written whole, and read back as the gateway kept it.
  const write = useCallback(async (next: ProvidersRow): Promise<void> => (await saveProvidersRow(credentials, next), await reread()), [credentials, reread]);

  if (door.value === undefined) return door.refused === null ? <p className="dash-quiet tst-none">Reading…</p> : <Refusal>{door.refused}</Refusal>;
  const row = door.value;
  const known: Known = { catalogue: catalogue.value, held: vendors.value ?? [], names: row.names ?? {} };
  const keyed = (stage: Stage): boolean => vendors.value === undefined || vendors.value.includes(stage.vendor);
  const save = (next: ProvidersRow): void => void acting.move(() => write(next)).then(close, () => undefined);
  const model = row.defaults["llm"];
  const judge = row.judge ?? null;
  const caller = row.caller ?? null;
  const stageRow = (name: string, does: string, stage: Stage | undefined, extra: string | null, onChange: () => void): ReactNode => (
    <div key={name} className="tst-row bxs-row">
      <span className="tst-row-words">
        <span className="tst-row-name">
          {name}
          <span className="tst-tag">{does}</span>
        </span>
        <span className="tst-row-under dash-clip">
          {stage === undefined ? "Nothing chosen" : stageSaid(known, stage)}
          {extra === null ? "" : ` · ${extra}`}
        </span>
      </span>
      {stage !== undefined && <span className={`tst-status bxs-status tst-status-${keyed(stage) ? "held" : "waiting"}`}>{keyed(stage) ? "Ready" : "No key here"}</span>}
      <button type="button" className="app-button" onClick={onChange}>
        Change
      </button>
    </div>
  );

  return (
    <>
      {open === null && <Refusal>{acting.refused}</Refusal>}
      <Section icon="route" title="What a call runs on" about="Used when an agent says nothing. An agent's own choice, in its code or its settings, always wins over these.">
        {STAGES.map((name) => {
          const stage = row.defaults[name];
          const fallbacks = stage?.fallbacks ?? [];
          return stageRow(STAGE_ABOUT[name].name, STAGE_ABOUT[name].does, stage, fallbacks.length === 0 ? "nobody takes over if it fails" : `then ${fallbacks.map((one) => stageSaid(known, one)).join(", then ")}`, () => setOpen({ stage: name }));
        })}
      </Section>

      <Section icon="judges" title="Judges and simulated callers" about="They run on this deployment's keys, unless an organization or an agent names its own model.">
        {stageRow("Judge", "Grades calls after they end.", judge?.llm, judge === null ? null : `at most $${judge.ceiling_usd} a call`, () => setOpen("judge"))}
        {stageRow("Simulated caller", "Plays the customer in a test call.", caller?.llm ?? model, `${caller?.llm == null ? "the default Model" : "its own model"}, ${caller?.ceiling_usd == null ? "no cap" : `at most $${caller.ceiling_usd} a call`}`, () => setOpen("caller"))}
      </Section>

      <DefaultVoices row={row} known={known} write={write} />
      <DefaultRates row={row} write={write} />

      <Section icon="tools" title="Advanced" about="For whoever knows the vendors' own settings. Most deployments never touch these.">
        <div className="tst-row bxs-row">
          <span className="tst-row-words">
            <span className="tst-row-name">Languages also listened for</span>
            <span className="tst-row-under">{row.hints.length === 0 ? "None: a call listens for its agent's language alone." : row.hints.join(", ")}</span>
          </span>
          <button type="button" className="app-button" onClick={() => setOpen("hints")}>
            Change
          </button>
        </div>
        <div className="tst-row bxs-row">
          <span className="tst-row-words">
            <span className="tst-row-name">Vendor tuning</span>
            <span className="tst-row-under">{Object.keys(row.tuning).length === 0 ? "Nothing is tuned." : `${Object.keys(row.tuning).length} vendors or models are told something of their own.`}</span>
          </span>
          <button type="button" className="app-button" onClick={() => setOpen("tuning")}>
            Change
          </button>
        </div>
        <div className="tst-row bxs-row">
          <span className="tst-row-words">
            <span className="tst-row-name">
              Knowledge embedder
              <span className="tst-tag">read only</span>
            </span>
            <span className="tst-row-under dash-clip">
              {row.embedding == null ? "None: knowledge bases and memory are off on this deployment." : `${brandOf(row.embedding.vendor)} · ${row.embedding.model}${row.embedding.dimensions == null ? "" : ` · ${row.embedding.dimensions} dimensions`}. Changing it would mean indexing every organization's knowledge and memory again, so it is not changed here.`}
            </span>
          </span>
        </div>
      </Section>

      {open !== null && typeof open === "object" && (
        <StagePanel
          key={open.stage}
          title={`Default ${STAGE_ABOUT[open.stage].name.toLowerCase()}`}
          icon={STAGE_ABOUT[open.stage].icon}
          about={STAGE_ABOUT[open.stage].panel}
          effect="Every agent on this deployment that chose nothing runs on this from its next call, in every organization. Agents that chose their own are not touched."
          modality={open.stage}
          stage={row.defaults[open.stage] ?? { vendor: "" }}
          known={known}
          saving={acting.busy}
          refused={acting.refused}
          onSave={(stage) => save({ ...row, defaults: { ...row.defaults, [open.stage]: stage } })}
          onClose={close}
        />
      )}
      {open === "judge" && (
        <SpendPanel
          title="Judge"
          icon="judges"
          about="The model that grades a call once it has ended."
          effect="Every organization's calls are graded by this model from the next one, unless the organization or the agent named its own. Each verdict counts as one of its evaluations."
          spend={{ llm: judge?.llm ?? model ?? { vendor: "" }, ceiling: judge?.ceiling_usd ?? null }}
          mayFollow={false}
          mustCap
          capAbout="Past it, the judges left for that call are skipped."
          known={known}
          saving={acting.busy}
          refused={acting.refused}
          onSave={(spend) => save({ ...row, judge: { ...(judge ?? {}), llm: spend.llm ?? { vendor: "" }, ceiling_usd: spend.ceiling ?? 0 } })}
          onClose={close}
        />
      )}
      {open === "caller" && (
        <SpendPanel
          title="Simulated caller"
          icon="simulations"
          about="The pretend customer that calls an agent in a simulation."
          effect="Every simulation on this deployment is played by this model from the next one, where its persona names none. It always runs on this deployment's keys."
          spend={{ llm: caller?.llm ?? null, ceiling: caller?.ceiling_usd ?? null }}
          mayFollow
          mustCap={false}
          capAbout="Past it, the caller hangs up. Empty, it spends what its turns ask."
          known={known}
          saving={acting.busy}
          refused={acting.refused}
          onSave={(spend) => save({ ...row, caller: spend.llm === null && spend.ceiling === null ? null : { ...(spend.ceiling === null ? {} : { ceiling_usd: spend.ceiling }), ...(spend.llm === null ? {} : { llm: spend.llm }) } })}
          onClose={close}
        />
      )}
      {open === "hints" && <HintsPanel hints={row.hints} saving={acting.busy} refused={acting.refused} onSave={(hints) => save({ ...row, hints })} onClose={close} />}
      {open === "tuning" && <TuningPanel tuning={row.tuning} saving={acting.busy} refused={acting.refused} onSave={(tuning) => save({ ...row, tuning })} onClose={close} />}
    </>
  );
}
