/** Defaults: what a call runs on when neither the agent nor its settings chose — the stages, voices, judge, caller, prices. */

import { Fragment, useCallback, useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readCatalogue, type Catalogue } from "../../lib/catalogue";
import { Button, Card, CardHead, Field, Input, KV, Refused, TextArea, TextAction } from "../../ui";
import { DefaultRates } from "./defaults-rates";
import { StageEditor } from "./defaults-stage";
import { DefaultVoices } from "./defaults-voices";
import { readBoxVendors } from "./door-box";
import { readProvidersRow, saveProvidersRow, STAGES, type ProvidersRow, type Stage } from "./door-providers";
import { useDoor, useMove } from "./use-door";

const STAGE_NAMED = { stt: "Ears", llm: "Model", tts: "Voice" } as const;

/** The row as it is written: a voice nobody picked is left out, since an empty voice is a silent call. */
export function written(row: ProvidersRow): ProvidersRow {
  return { ...row, voices: Object.fromEntries(Object.entries(row.voices).filter(([, voice]) => voice.trim() !== "")) };
}

/**
 * The whole row is a draft until Save writes it whole: the gateway checks every vendor is
 * installed and does its stage, and refuses the row otherwise, naming what is wrong.
 */
export function SettingsDefaults(): ReactNode {
  const credentials = useCredentials();
  const row = useDoor(useCallback(() => readProvidersRow(credentials), [credentials]));
  const vendors = useDoor(useCallback(() => readBoxVendors(credentials), [credentials]));
  const acting = useMove();
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [draft, setDraft] = useState<ProvidersRow | null>(null);
  const [tuning, setTuning] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let gone = false;
    readCatalogue(credentials).then((read) => {
      if (!gone) setCatalogue(read);
    }, () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials]);

  if (row.value === undefined) return <Refused>{row.refused}</Refused>;
  const shown = draft ?? row.value;
  const held = vendors.value ?? [];
  const change = (next: Partial<ProvidersRow>): void => {
    setDraft({ ...shown, ...next });
    setSaved(false);
  };
  const setStage = (name: string, stage: Stage): void => change({ defaults: { ...shown.defaults, [name]: stage } });

  const save = async (): Promise<void> => {
    const done = await acting.move(async () => {
      const parsed = tuning === null ? shown.tuning : (JSON.parse(tuning) as Record<string, unknown>);
      await saveProvidersRow(credentials, written({ ...shown, tuning: parsed }));
      await row.reread();
    });
    if (done) {
      setDraft(null);
      setTuning(null);
      setSaved(true);
    }
  };

  return (
    <>
      <Card>
        <CardHead title="What a call runs on when nobody chose" meta="the agent's class and its settings win over these" />
        <div className="box-body">
          <div className="box-stage-grid">
            <span />
            <span className="box-caption">Vendor</span>
            <span className="box-caption">Model</span>
            <span className="box-caption">Falls back to, in order, when it fails</span>
            {STAGES.map((name) => (
              <Fragment key={name}>
                <span className="box-stage-name">{STAGE_NAMED[name]}</span>
                <StageEditor modality={name} stage={shown.defaults[name] ?? { vendor: "" }} catalogue={catalogue} held={held} withFallbacks onChange={(stage) => setStage(name, stage)} />
              </Fragment>
            ))}
          </div>
          <div className="box-limit-about">
            A model left empty is the vendor plugin's own. A vendor marked “no box key” runs only for an org that brought its own key for it (Keys tab).
          </div>
        </div>
      </Card>

      <DefaultVoices voices={shown.voices} tts={shown.defaults["tts"]?.vendor ?? ""} onChange={(voices) => change({ voices })} />

      <Card>
        <CardHead title="Judges and simulated callers" meta="they run on the box's keys, unless the org or agent names its own model" />
        <div className="box-body">
          <div className="box-judge-grid">
            <span />
            <span className="box-caption">Vendor</span>
            <span className="box-caption">Model</span>
            <span className="box-caption">May spend per call, $</span>

            <span className="box-stage-name">Judge</span>
            <StageEditor
              modality="llm"
              stage={shown.judge?.llm ?? { vendor: shown.defaults["llm"]?.vendor ?? "" }}
              catalogue={catalogue}
              held={held}
              withFallbacks={false}
              onChange={(llm) => change({ judge: { ceiling_usd: shown.judge?.ceiling_usd ?? 0.05, llm } })}
            />
            <Input
              inputMode="decimal"
              value={String(shown.judge?.ceiling_usd ?? "")}
              onChange={(event) => change({ judge: { llm: shown.judge?.llm ?? { vendor: shown.defaults["llm"]?.vendor ?? "" }, ceiling_usd: Number(event.target.value) } })}
            />

            <span className="box-stage-name">Simulated caller</span>
            {shown.caller?.llm ? (
              <StageEditor modality="llm" stage={shown.caller.llm} catalogue={catalogue} held={held} withFallbacks={false} onChange={(llm) => change({ caller: { ceiling_usd: shown.caller?.ceiling_usd ?? 0.2, llm } })} />
            ) : (
              <span className="box-judge-default">
                the Model above <TextAction onClick={() => change({ caller: { ceiling_usd: shown.caller?.ceiling_usd ?? 0.2, llm: shown.defaults["llm"] ?? { vendor: "" } } })}>Choose another</TextAction>
              </span>
            )}
            <Input
              inputMode="decimal"
              value={String(shown.caller?.ceiling_usd ?? "")}
              placeholder="what its turns ask"
              onChange={(event) =>
                change({ caller: event.target.value.trim() === "" ? null : { ...(shown.caller?.llm ? { llm: shown.caller.llm } : {}), ceiling_usd: Number(event.target.value) } })
              }
            />
          </div>
        </div>
      </Card>

      <DefaultRates rates={shown.rates} onChange={(rates) => change({ rates })} />

      <Card>
        <CardHead title="Embedder" meta="shown, not edited here: changing it re-indexes every base and fact of every org" />
        {shown.embedding ? (
          <div className="box-kvs">
            <KV label="Model" keyWidth={120}>
              <span className="box-fixed">
                {shown.embedding.vendor} · {shown.embedding.model} · {shown.embedding.dimensions ?? ""} dims
              </span>
            </KV>
            <KV label="At" keyWidth={120}>
              <span className="box-fixed">{shown.embedding.url}</span>
            </KV>
          </div>
        ) : (
          <span className="ui-note">No embedder: knowledge bases and memory are off on this box.</span>
        )}
      </Card>

      <Card>
        <CardHead title="Advanced" meta="languages the ears also listen for, and what each vendor or model is told, by its own field names" />
        <div className="box-body">
        <Field label="Languages the ears also listen for">
          <Input value={shown.hints.join(", ")} placeholder="es, pt" onChange={(event) => change({ hints: event.target.value.split(",").map((one) => one.trim()).filter((one) => one !== "") })} />
        </Field>
        <Field label="Tuning, as JSON">
          <TextArea rows={10} value={tuning ?? JSON.stringify(shown.tuning, null, 2)} onChange={(event) => { setTuning(event.target.value); setSaved(false); }} />
        </Field>
        </div>
      </Card>

      <div className="box-save">
        <Button kind="primary" size="md" disabled={acting.busy || (draft === null && tuning === null)} onClick={() => void save()}>
          {acting.busy ? "Saving…" : "Save the defaults"}
        </Button>
        {(draft !== null || tuning !== null) && <TextAction onClick={() => { setDraft(null); setTuning(null); }}>Discard</TextAction>}
        {saved && <span className="box-done">Saved. The next call runs on it.</span>}
      </div>
      <Refused>{acting.refused}</Refused>
    </>
  );
}
