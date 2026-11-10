/** Where the organization's alerts go: its admins' mail always, and a webhook when one is set, tried from here. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { dropWebhook, putWebhook, readWebhook, testWebhook, type Webhook } from "./door";

export function WebhookCard(): ReactNode {
  const credentials = useCredentials();
  // Undefined while asked, or for a key that may not read it: the card is not drawn.
  const [webhook, setWebhook] = useState<Webhook | null | undefined>(undefined);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ good: boolean; text: string } | null>(null);

  useEffect(() => {
    readWebhook(credentials).then(setWebhook, () => undefined);
  }, [credentials]);

  const act = async (doing: () => Promise<string | null>): Promise<void> => {
    setBusy(true);
    setSaid(null);
    try {
      const text = await doing();
      if (text !== null) setSaid({ good: true, text });
      setWebhook(await readWebhook(credentials));
    } catch (failed) {
      setSaid({ good: false, text: saidBy(failed) });
    } finally {
      setBusy(false);
    }
  };

  if (webhook === undefined) return null;
  const keep = (event: FormEvent): void => {
    event.preventDefault();
    void act(async () => (await putWebhook(credentials, url.trim(), secret.trim() === "" ? null : secret.trim()), setUrl(""), setSecret(""), "Kept. Send a test to see it arrive."));
  };
  const test = async (): Promise<string | null> => {
    const tried = await testWebhook(credentials);
    if (!tried.sent) throw new Error(tried.error ?? "The URL did not answer 2xx.");
    return "The test post arrived.";
  };

  return (
    <section className="dash-card mon-hook" aria-label="Where alerts go">
      <span className="dash-eyebrow dash-eyebrow-head">Where alerts go</span>
      <p className="dash-quiet">Every alert is kept here and mailed to the organization's admins. A webhook also gets each one as a POST.</p>
      {webhook === null ? (
        <form className="mon-hook-form" onSubmit={keep}>
          <input className="cfg-input" type="url" aria-label="Webhook URL" placeholder="https://example.com/pinecall-alerts" required value={url} onChange={(event) => setUrl(event.target.value)} />
          <input className="cfg-input mon-hook-secret" type="password" aria-label="Signing secret" placeholder="Signing secret, optional" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} />
          <button type="submit" className="app-button" disabled={busy}>
            {busy ? "Saving…" : "Set webhook"}
          </button>
        </form>
      ) : (
        <div className="mon-hook-set">
          <code className="dash-clip">{webhook.url}</code>
          <span className="tst-tag">{webhook.signed ? "signed" : "not signed"}</span>
          <button type="button" className="app-button" disabled={busy} onClick={() => void act(test)}>
            {busy ? "Sending…" : "Send a test"}
          </button>
          <ConfirmButton label="Remove" asks="Remove the webhook?" danger onConfirm={() => void act(async () => (await dropWebhook(credentials), null))} />
        </div>
      )}
      {said !== null && <p className={said.good ? "mon-hook-good" : "cfg-refused"}>{said.text}</p>}
    </section>
  );
}
