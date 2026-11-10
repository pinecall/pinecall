/** Where the org sends its calls' traces, in the side panel: Langfuse by its two keys, or any OpenTelemetry collector by its URL and headers, never shown back. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { Select } from "../ui/select";
import { Field, Toggle } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { dropCollector, isLangfuse, langfuseAs, LANGFUSE_REGIONS, putCollector, readCollector, type Collector, type Wanted } from "./telemetry-door";
import "../configure/configure.css";

const WIDTH = 480;

interface FormProps {
  busy: boolean;
  replacing: boolean;
  onSave: (wanted: Wanted) => void;
  onRefuse: (why: string) => void;
}

function Text({ on, onChange, off }: { on: boolean; onChange: (on: boolean) => void; off: string }): ReactNode {
  return (
    <div className="ob-tel-text">
      <Toggle on={on} label="Include what was said" onChange={onChange} />
      <span className="ob-tel-text-words">
        <span>Include what was said and what each tool returned</span>
        <span className="dash-quiet">{on ? "Each step is sent with its input and its output." : off}</span>
      </span>
    </div>
  );
}

function LangfuseForm({ busy, replacing, onSave }: FormProps): ReactNode {
  const [region, setRegion] = useState("eu");
  const [host, setHost] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [pii, setPii] = useState(true);
  const base = region === "own" ? host.trim() : (LANGFUSE_REGIONS.find((one) => one.value === region)?.base ?? "");
  const ready = /^https?:\/\//.test(base) && publicKey.trim().startsWith("pk-lf-") && secretKey.trim().startsWith("sk-lf-") && !busy;

  const save = (event: FormEvent): void => {
    event.preventDefault();
    if (ready) onSave(langfuseAs(base, publicKey.trim(), secretKey.trim(), pii));
  };

  return (
    <form className="ob-tel-form" onSubmit={save}>
      <Field label="Langfuse region">
        <Select label="Langfuse region" value={region} onChange={setRegion} items={LANGFUSE_REGIONS.map((one) => ({ value: one.value, label: one.label, detail: one.base === "" ? "Your own address" : new URL(one.base).host }))} />
      </Field>
      {region === "own" && (
        <Field label="Address of your Langfuse">
          <input className="cfg-input" value={host} placeholder="https://langfuse.example.com" autoComplete="off" spellCheck={false} onChange={(event) => setHost(event.target.value)} />
        </Field>
      )}
      <Field label="Public key">
        <input className="cfg-input" value={publicKey} placeholder="pk-lf-…" autoComplete="off" spellCheck={false} onChange={(event) => setPublicKey(event.target.value)} />
      </Field>
      <Field label="Secret key">
        <input className="cfg-input" type="password" value={secretKey} placeholder="sk-lf-…" autoComplete="new-password" onChange={(event) => setSecretKey(event.target.value)} />
        <span className="dash-quiet">Stored encrypted, never shown again.</span>
      </Field>
      <Text on={pii} onChange={setPii} off="Langfuse gets only timings, token counts and names." />
      <button type="submit" className="cfg-save ob-tel-save" disabled={!ready}>
        {busy ? "Saving…" : replacing ? "Replace with Langfuse" : "Send traces to Langfuse"}
      </button>
    </form>
  );
}

/** One header of the form: the value is sent once and never read back. */
interface Header {
  name: string;
  value: string;
}

const NO_HEADER: Header = { name: "", value: "" };

function CollectorForm({ busy, replacing, onSave, onRefuse }: FormProps): ReactNode {
  const [endpoint, setEndpoint] = useState("");
  const [headers, setHeaders] = useState<Header[]>([NO_HEADER]);
  const [pii, setPii] = useState(false);

  const setHeader = (at: number, change: Partial<Header>): void => setHeaders(headers.map((one, index) => (index === at ? { ...one, ...change } : one)));

  const save = (event: FormEvent): void => {
    event.preventDefault();
    const url = endpoint.trim();
    const named = headers.filter((one) => one.name.trim() !== "" || one.value !== "");
    if (!/^https?:\/\//.test(url)) return onRefuse("The collector is an http(s) URL an OpenTelemetry exporter can post to.");
    if (named.some((one) => one.name.trim() === "" || one.value === "")) return onRefuse("A header has a name and a value.");
    onSave({ endpoint: url, headers: Object.fromEntries(named.map((one) => [one.name.trim(), one.value])), pii });
  };

  return (
    <form className="ob-tel-form" onSubmit={save}>
      <Field label="Collector URL">
        <input className="cfg-input" value={endpoint} placeholder="https://otlp.datadoghq.eu/v1/traces" autoComplete="off" spellCheck={false} onChange={(event) => setEndpoint(event.target.value)} />
        <span className="dash-quiet">OpenTelemetry over HTTP, traces.</span>
      </Field>
      <Field label="Headers">
        {headers.map((one, at) => (
          <div key={at} className="ob-tel-header">
            <input className="cfg-input" aria-label="Header name" value={one.name} placeholder="dd-api-key" autoComplete="off" spellCheck={false} onChange={(event) => setHeader(at, { name: event.target.value })} />
            <input className="cfg-input" aria-label="Header value" type="password" value={one.value} placeholder="Its value" autoComplete="new-password" onChange={(event) => setHeader(at, { value: event.target.value })} />
          </div>
        ))}
        <span className="dash-quiet">Headers usually carry the tool's API key. Stored encrypted, never shown again.</span>
        <button type="button" className="app-button ob-tel-more" onClick={() => setHeaders([...headers, NO_HEADER])}>
          Add another header
        </button>
      </Field>
      <Text on={pii} onChange={setPii} off="Only timings, token counts and names are sent." />
      <button type="submit" className="cfg-save ob-tel-save" disabled={busy || endpoint.trim() === ""}>
        {busy ? "Saving…" : replacing ? "Replace" : "Connect"}
      </button>
    </form>
  );
}

/**
 * A copy of every spoken call's spans goes over OTLP to the collector named here; a chat has no
 * worker and so no spans. The headers are a credential: typed here, sent once, kept sealed by the
 * gateway; the panel reads back their names alone.
 */
export function TelemetryPanel({ onClose }: { onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [collector, setCollector] = useState<Collector | null | undefined>(undefined);
  const [langfuse, setLangfuse] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // A form that was kept starts over: what was typed is a credential, and it was sent.
  const [kept, setKept] = useState(0);

  useEffect(() => {
    let gone = false;
    readCollector(credentials).then(
      (found) => !gone && setCollector(found),
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const keep = async (wanted: Wanted): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      await putCollector(credentials, wanted);
      setCollector(await readCollector(credentials));
      setKept((was) => was + 1);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const forget = async (): Promise<void> => {
    setRefused(null);
    try {
      await dropCollector(credentials);
      setCollector(null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const form: FormProps = { busy, replacing: collector != null, onSave: (wanted) => void keep(wanted), onRefuse: setRefused };

  return (
    <SidePanel title="Send traces" icon="wave" about="Send a copy of every voice and phone call's trace to your own tool, such as Langfuse or Datadog: each model request, what was heard and said, each tool call, with timings and token counts. Chats are not traced." width={WIDTH} onClose={onClose}>
      <div className="ob-tel-now">
        <span className="dash-eyebrow">
          <span className={collector == null ? "app-dot app-dot-calm" : "app-dot app-dot-good"} aria-hidden="true" />
          {collector === undefined ? "Where traces go" : collector === null ? "Not connected" : "Connected"}
        </span>
        {collector === null && <p className="dash-quiet">Traces stay in Pinecall only. Connect a tool below to also send them there.</p>}
        {collector != null && (
          <>
            <dl className="ob-facts ob-facts-wide">
              <div>
                <dt>Sent to</dt>
                <dd className="ob-break">{isLangfuse(collector.endpoint) ? `Langfuse, ${new URL(collector.endpoint).host}` : collector.endpoint}</dd>
              </div>
              <div>
                <dt>Credentials</dt>
                <dd className="ob-break">{collector.header_names.length > 0 ? `${collector.header_names.join(", ")} (saved, never shown)` : "None"}</dd>
              </div>
              <div>
                <dt>Conversation text</dt>
                <dd>{collector.pii ? "Included in the traces." : "Left out. Only timings, token counts and names are sent."}</dd>
              </div>
            </dl>
            <ConfirmButton label="Stop sending" asks="Stop sending? Traces stay in Pinecall" danger onConfirm={() => void forget()} />
          </>
        )}
      </div>

      <div className="dash-switch ob-tel-kind" role="group" aria-label="Which tool">
        <button type="button" aria-pressed={langfuse} className={langfuse ? "dash-switch-on" : ""} onClick={() => setLangfuse(true)}>
          Langfuse
        </button>
        <button type="button" aria-pressed={!langfuse} className={langfuse ? "" : "dash-switch-on"} onClick={() => setLangfuse(false)}>
          Other (OpenTelemetry)
        </button>
      </div>
      {langfuse ? <LangfuseForm key={kept} {...form} /> : <CollectorForm key={kept} {...form} />}
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
    </SidePanel>
  );
}
