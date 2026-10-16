/** Langfuse as the org's collector: a region and the project's two keys, turned into the OTLP URL and the headers Langfuse asks for. */

import { useState, type FormEvent, type ReactNode } from "react";

import { Button, Check, Field, Input, Select, SelectItem } from "../../ui";

// Langfuse takes OpenTelemetry over HTTP at /api/public/otel (langfuse.com/integrations/native/opentelemetry).
const REGIONS = [
  { value: "eu", label: "EU · cloud.langfuse.com", base: "https://cloud.langfuse.com" },
  { value: "us", label: "US · us.cloud.langfuse.com", base: "https://us.cloud.langfuse.com" },
  { value: "jp", label: "Japan · jp.cloud.langfuse.com", base: "https://jp.cloud.langfuse.com" },
  { value: "hipaa", label: "HIPAA · hipaa.cloud.langfuse.com", base: "https://hipaa.cloud.langfuse.com" },
  { value: "own", label: "Self-hosted", base: "" },
] as const;

type Region = (typeof REGIONS)[number]["value"];

/** Where an OTLP exporter posts a Langfuse project's traces, from its host. */
export function langfuseTraces(host: string): string {
  return `${host.replace(/\/+$/, "")}/api/public/otel/v1/traces`;
}

/** Whether a collector is Langfuse's, by its path. */
export function isLangfuse(endpoint: string): boolean {
  return endpoint.includes("/api/public/otel/");
}

/**
 * The headers a Langfuse project takes: Basic auth of the public and the secret key, and the
 * ingestion version that shows a trace at once instead of up to ten minutes later.
 */
export function langfuseHeaders(publicKey: string, secretKey: string): Record<string, string> {
  return { Authorization: `Basic ${btoa(`${publicKey}:${secretKey}`)}`, "x-langfuse-ingestion-version": "4" };
}

export function LangfuseForm({ busy, replacing, onSave }: { busy: boolean; replacing: boolean; onSave: (endpoint: string, headers: Record<string, string>, pii: boolean) => void }): ReactNode {
  const [region, setRegion] = useState<Region>("eu");
  const [host, setHost] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [pii, setPii] = useState(true);
  const base = region === "own" ? host.trim() : REGIONS.find((one) => one.value === region)?.base ?? "";
  const ready = /^https?:\/\//.test(base) && publicKey.trim().startsWith("pk-lf-") && secretKey.trim().startsWith("sk-lf-") && !busy;

  const save = (event: FormEvent): void => {
    event.preventDefault();
    if (ready) onSave(langfuseTraces(base), langfuseHeaders(publicKey.trim(), secretKey.trim()), pii);
  };

  return (
    <form className="tel-form" onSubmit={save}>
      <div className="tel-fields">
      <Field label="Langfuse region" minWidth={260}>
        <Select value={region} onValueChange={(value) => setRegion(value as Region)} aria-label="Langfuse region">
          {REGIONS.map((one) => (
            <SelectItem key={one.value} value={one.value}>
              {one.label}
            </SelectItem>
          ))}
        </Select>
      </Field>
      {region === "own" && (
        <Field label="Address of your Langfuse" grow minWidth={280}>
          <Input value={host} placeholder="https://langfuse.example.com" autoComplete="off" spellCheck={false} onChange={(event) => setHost(event.target.value)} />
        </Field>
      )}
      <Field label="Public key" minWidth={220}>
        <Input value={publicKey} placeholder="pk-lf-…" autoComplete="off" spellCheck={false} onChange={(event) => setPublicKey(event.target.value)} />
      </Field>
      <Field label="Secret key" grow minWidth={220}>
        <Input type="password" value={secretKey} placeholder="sk-lf-…" autoComplete="new-password" onChange={(event) => setSecretKey(event.target.value)} />
        <div className="tel-hint">Stored encrypted, never shown again.</div>
      </Field>
      </div>
      <Check checked={pii} onChange={setPii}>
        Include what was said and what each tool returned
      </Check>
      <div className="tel-hint">Off, Langfuse gets only timings, token counts and names. On, it also shows each step's input and output.</div>
      <Button kind="primary" size="form" type="submit" disabled={!ready}>
        {busy ? "Saving…" : replacing ? "Replace with Langfuse" : "Send traces to Langfuse"}
      </Button>
    </form>
  );
}
