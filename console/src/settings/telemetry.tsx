/** Telemetry: the collector the org's calls' traces go to, any OpenTelemetry one by its URL and headers, set, read back by name and taken away. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { Icon } from "../shell/icons";
import { Field, Setting, Toggle } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { dropCollector, keepCollector, readCollector, type Collector } from "./door";

function CollectorPanel({ was, onKept, onClose }: { was: Collector | null; onKept: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [endpoint, setEndpoint] = useState(was?.endpoint ?? "");
  // A header's value is never read back: replacing the collector means typing them again.
  const [headers, setHeaders] = useState<[string, string][]>(() => [...(was?.header_names ?? []).map((name): [string, string] => [name, ""]), ["", ""]]);
  const [pii, setPii] = useState(was?.pii ?? false);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const setHeader = (at: number, row: [string, string]): void => {
    const next = headers.map((one, index) => (index === at ? row : one));
    setHeaders(next.at(-1)?.some((part) => part !== "") === true ? [...next, ["", ""]] : next);
  };
  const keep = (event: FormEvent): void => {
    event.preventDefault();
    const named = headers.filter(([name]) => name.trim() !== "");
    if (named.some(([, value]) => value === "")) return setRefused("Type each header's value: they are never read back, so they are sent again whole.");
    setBusy(true);
    setRefused(null);
    keepCollector(credentials, { endpoint: endpoint.trim(), headers: Object.fromEntries(named.map(([name, value]) => [name.trim(), value])), pii }).then(() => (onKept(), onClose()), (failed: unknown) => setRefused(saidBy(failed))).finally(() => setBusy(false));
  };
  return (
    <SidePanel
      title="Trace collector"
      icon="observability"
      about="Every spoken call is traced over OTLP: each turn, each model call, each tool. Langfuse, Honeycomb, Datadog, or any OpenTelemetry collector takes them."
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form="collector" className="cfg-save" disabled={busy || endpoint.trim() === ""}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </>
      }
    >
      <form id="collector" className="cfg-dialog-body" onSubmit={keep}>
        <Field label="Endpoint">
          <input className="cfg-input" type="url" aria-label="Endpoint" placeholder="https://cloud.langfuse.com/api/public/otel/v1/traces" required spellCheck={false} value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
        </Field>
        <Field label="Headers">
          <div className="set-headers">
            {headers.map(([name, value], at) => (
              <div key={at} className="set-header">
                <input className="cfg-input" aria-label="Header" placeholder="Authorization" spellCheck={false} autoComplete="off" value={name} onChange={(event) => setHeader(at, [event.target.value, value])} />
                <input className="cfg-input" type="password" aria-label="Its value" placeholder="Its value" autoComplete="new-password" value={value} onChange={(event) => setHeader(at, [name, event.target.value])} />
              </div>
            ))}
          </div>
        </Field>
        <Setting icon="privacy" title="Include what was said" about="Off, a trace carries timings, token counts and names alone. On, the words of the call and the prompt go with it." aside={<Toggle on={pii} label="Include what was said" onChange={setPii} />} />
      </form>
    </SidePanel>
  );
}

export function Telemetry(): ReactNode {
  const credentials = useCredentials();
  const [collector, setCollector] = useState<Collector | null | undefined>(undefined);
  const [refused, setRefused] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const close = useCallback(() => setEditing(false), []);
  const reread = useCallback((): void => void readCollector(credentials).then(setCollector, (failed: unknown) => (setCollector(null), setRefused(saidBy(failed)))), [credentials]);
  useEffect(reread, [reread]);

  return (
    <>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      <section className="tst-list set-tone-good" aria-label="Telemetry">
        <header className="tst-head">
          <span className="tst-head-mark" aria-hidden="true">
            <Icon name="observability" size={16} />
          </span>
          <span className="tst-head-words">
            <span className="tst-head-title">Telemetry</span>
            <span className="tst-head-about">Where your calls' traces are sent, beside what Observability shows here.</span>
          </span>
          {collector !== undefined && (
            <button type="button" className="cfg-save tst-action" onClick={() => setEditing(true)}>
              {collector === null ? "Connect a collector" : "Replace"}
            </button>
          )}
        </header>
        {collector === undefined && <p className="dash-quiet tst-none">Reading…</p>}
        {collector === null && <p className="dash-quiet tst-none">No collector of your own. Traces stay on Pinecall.</p>}
        {collector != null && (
          <div className="tst-row set-row">
            <span className="tst-row-words">
              <span className="tst-row-name">
                <code className="set-code dash-clip">{collector.endpoint}</code>
              </span>
              <span className="tst-row-under dash-clip">
                {collector.header_names.length === 0 ? "No header" : `Headers: ${collector.header_names.join(", ")}`}. {collector.pii ? "What was said is included." : "What was said is left out."}
              </span>
            </span>
            <ConfirmButton label="Disconnect" asks="Stop sending traces?" danger onConfirm={() => void dropCollector(credentials).then(reread, (failed: unknown) => setRefused(saidBy(failed)))} />
          </div>
        )}
      </section>
      {editing && <CollectorPanel was={collector ?? null} onKept={reread} onClose={close} />}
    </>
  );
}
