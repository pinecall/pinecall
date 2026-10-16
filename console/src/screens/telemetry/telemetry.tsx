/** Telemetry: where the org sends its calls' traces — Langfuse by its two keys, or any OpenTelemetry collector by its URL and headers, never shown back. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Check, Field, Input, KV, Page, PageHead, Pill, Refused, Segmented, TextAction } from "../../ui";
import { dropCollector, putCollector, readCollector, type Collector } from "../../lib/telemetry";
import { isLangfuse, LangfuseForm } from "./langfuse";
import "./telemetry.css";

type Kind = "langfuse" | "otlp";

/** One header of the form: a name and a value, the value sent once and never read back. */
interface Header {
  name: string;
  value: string;
}

/**
 * A copy of every spoken call's spans — the model's requests, speech in and out, every tool — goes
 * over OTLP to the collector named here; a chat has no worker and so no spans. The headers are a
 * credential: typed here, sent once, and the gateway keeps them sealed; the page reads back their
 * names alone.
 */
export function Telemetry(): ReactNode {
  const credentials = useCredentials();
  const [collector, setCollector] = useState<Collector | null | undefined>(undefined);
  const [endpoint, setEndpoint] = useState("");
  const [headers, setHeaders] = useState<Header[]>([{ name: "", value: "" }]);
  const [pii, setPii] = useState(false);
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<Kind>("langfuse");
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readCollector(credentials).then(
      (found) => {
        if (!gone) setCollector(found);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const kept = async (url: string, sent: Record<string, string>, carries: boolean): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      await putCollector(credentials, url, sent, carries);
      setCollector(await readCollector(credentials));
      setEndpoint("");
      setHeaders([{ name: "", value: "" }]);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const url = endpoint.trim();
    const named = headers.filter((one) => one.name.trim() !== "" || one.value !== "");
    const half = named.find((one) => one.name.trim() === "" || one.value === "");
    if (!/^https?:\/\//.test(url)) {
      setRefused("The collector is an http(s) URL an OTLP exporter can post to.");
      return;
    }
    if (half !== undefined) {
      setRefused("A header has a name and a value.");
      return;
    }
    await kept(url, Object.fromEntries(named.map((one) => [one.name.trim(), one.value])), pii);
  };

  const forget = async (): Promise<void> => {
    if (!window.confirm("Stop sending traces to this tool? They stay in Pinecall either way.")) return;
    setRefused(null);
    try {
      await dropCollector(credentials);
      setCollector(null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const setHeader = (at: number, change: Partial<Header>): void => {
    setHeaders(headers.map((one, index) => (index === at ? { ...one, ...change } : one)));
  };

  return (
    <Page tight>
      <PageHead
        title="Telemetry"
        ledeWidth={660}
        lede="Send a copy of every voice and phone call's trace to your own tool, such as Langfuse or Datadog: each model request, what was heard and said, each tool call, with timings and token counts. Chats are not traced."
      />

      <Card>
        <CardHead title="Where traces go" action={collector === undefined ? undefined : <Pill tone={collector === null ? "gray" : "green"}>{collector === null ? "Not connected" : "Connected"}</Pill>} />
        {collector === null && <div className="tel-rows tel-hint">Traces stay in Pinecall only. Connect a tool below to also send them there.</div>}
        {collector !== undefined && collector !== null && (
          <div className="tel-rows">
            <KV label="Sent to" keyWidth={150}>
              {isLangfuse(collector.endpoint) ? `Langfuse · ${new URL(collector.endpoint).host}` : collector.endpoint}
            </KV>
            <KV label="Credentials" keyWidth={150}>
              {collector.header_names.length > 0 ? `${collector.header_names.join(", ")} (saved, never shown)` : "none"}
            </KV>
            <KV label="Conversation text" keyWidth={150}>
              {collector.pii ? "Included in the traces" : "Left out. Only timings, token counts and names are sent."}
            </KV>
            <div>
              <TextAction danger onClick={() => void forget()}>
                Stop sending
              </TextAction>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardHead title="Connect a tool" meta="Langfuse, or anything that accepts OpenTelemetry" />
        <div className="tel-rows">
          <Segmented
            options={[
              { value: "langfuse", label: "Langfuse" },
              { value: "otlp", label: "Other (OpenTelemetry)" },
            ]}
            value={kind}
            onChange={setKind}
          />
          {kind === "langfuse" ? (
            <LangfuseForm busy={busy} replacing={collector !== null && collector !== undefined} onSave={(url, sent, carries) => void kept(url, sent, carries)} />
          ) : (
            <form className="tel-form" onSubmit={(event) => void save(event)}>
              <div className="tel-fields">
                <Field label="Collector URL (OTLP over HTTP, traces)" grow minWidth={320}>
                  <Input value={endpoint} placeholder="https://otlp.datadoghq.eu/v1/traces" autoComplete="off" spellCheck={false} onChange={(event) => setEndpoint(event.target.value)} />
                </Field>
              </div>
              {headers.map((one, at) => (
                <div key={at} className="tel-fields">
                  <Field label="Header name" minWidth={200}>
                    <Input value={one.name} placeholder="dd-api-key" autoComplete="off" spellCheck={false} onChange={(event) => setHeader(at, { name: event.target.value })} />
                  </Field>
                  <Field label="Header value" grow minWidth={220}>
                    <Input type="password" value={one.value} autoComplete="new-password" onChange={(event) => setHeader(at, { value: event.target.value })} />
                  </Field>
                </div>
              ))}
              <div className="tel-hint">Headers usually carry the tool's API key. Stored encrypted, never shown again.</div>
              <div>
                <TextAction onClick={() => setHeaders([...headers, { name: "", value: "" }])}>Add another header</TextAction>
              </div>
              <Check checked={pii} onChange={setPii}>
                Include what was said and what each tool returned
              </Check>
              <div className="tel-hint">Off, only timings, token counts and names are sent.</div>
              <Button kind="primary" size="form" type="submit" disabled={busy || endpoint.trim() === ""}>
                {busy ? "Saving…" : collector ? "Replace" : "Connect"}
              </Button>
            </form>
          )}
        </div>
      </Card>

      <Refused>{refused}</Refused>
    </Page>
  );
}
