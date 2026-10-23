/** Alerts, a tab of Settings: where the org's alerts are posted — a webhook of its own, set with a secret, proven with a test — beside the bell. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, KV, Page, PageHead, Pill, Refused, TextAction } from "../../ui";
import { dropWebhook, putWebhook, readWebhook, testWebhook, type Webhook } from "./door";
import "./alerts.css";

/** What sends an alert, in plain words, with the event name a server receives. */
const POSTED: { type: string; name: string; when: string }[] = [
  { type: "monitor.fired", name: "A monitor fired", when: "A number you watch, like answer speed, went past the limit you set. At most once a day per monitor." },
  { type: "spend.unusual", name: "Unusual spend", when: "Today's calls cost three times a usual day. Once a day." },
  { type: "credits.exhausted", name: "Out of quota", when: "A call or message was refused because a limit ran out." },
  { type: "app.failed", name: "An app went down", when: "An app Pinecall hosts for you did not build, start or stay up. Once per failure; Apps says why." },
];

const A_POST = `POST <your URL>
content-type: application/json
x-pinecall-event: monitor.fired
x-pinecall-signature: sha256=<HMAC-SHA256 of the body, with your secret>

{"type":"monitor.fired","org":"org_…","env":"production","agent":"front-desk","at":1791567316.2,
 "data":{"monitor":"mon_…","name":"slow answers","metric":"e2e_median_s","above":true,
         "threshold":2.0,"value":2.41,"window_days":7,"agent":null,"env":"production","day":"2026-10-09"}}`;

/**
 * Every alert is written on the agent's log; this is where it also goes out. The secret is a
 * credential: typed here, sent once, kept sealed by the gateway, and the page reads back only
 * whether posts are signed.
 */
export function Alerts(): ReactNode {
  const credentials = useCredentials();
  const [webhook, setWebhook] = useState<Webhook | null | undefined>(undefined);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [tested, setTested] = useState<string | null>(null);
  const [example, setExample] = useState(false);

  useEffect(() => {
    let gone = false;
    readWebhook(credentials).then(
      (found) => {
        if (!gone) setWebhook(found);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const wanted = url.trim();
    if (!/^https?:\/\//.test(wanted)) {
      setRefused("The webhook is an http(s) URL an alert can be posted to.");
      return;
    }
    setBusy(true);
    setRefused(null);
    setTested(null);
    try {
      await putWebhook(credentials, wanted, secret === "" ? null : secret);
      setWebhook(await readWebhook(credentials));
      setUrl("");
      setSecret("");
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const test = async (): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      const answer = await testWebhook(credentials);
      setTested(answer.sent ? "It answered 2xx: the test post went through, signed as every alert is." : `It did not take it — ${answer.error ?? "no answer"}.`);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const forget = async (): Promise<void> => {
    if (!window.confirm("Stop posting alerts to this URL? They stay on the agents' logs and in the bell either way.")) return;
    setRefused(null);
    setTested(null);
    try {
      await dropWebhook(credentials);
      setWebhook(null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Page tight>
      <PageHead
        title="Alerts"
        ledeWidth={660}
        lede={
          <>
            Get a message in Slack, PagerDuty or your own server when something needs attention. People also get alerts in the bell; each person picks theirs under{" "}
            <Link to="/notifications">Notifications</Link>.
          </>
        }
      />

      <Card>
        <CardHead title="Where alerts are sent" action={webhook === undefined ? undefined : <Pill tone={webhook === null ? "gray" : "green"}>{webhook === null ? "Not connected" : "Connected"}</Pill>} />
        {webhook !== undefined && webhook !== null && (
          <div className="alr-rows">
            <KV label="URL" keyWidth={90}>
              <span className="ui-clip">{webhook.url}</span>
            </KV>
            <KV label="Signed" keyWidth={90}>
              {webhook.signed ? "Yes, with your secret" : "No. Add a secret to sign them."}
            </KV>
            <div className="alr-line">
              <Button size="sm" disabled={busy} onClick={() => void test()}>
                Send a test alert
              </Button>
              <TextAction danger onClick={() => void forget()}>
                Disconnect
              </TextAction>
              {tested !== null && <span className="alr-tested">{tested}</span>}
            </div>
          </div>
        )}
        <form className="alr-form" onSubmit={(event) => void save(event)}>
          <div className="alr-fields">
            <Field label={webhook ? "New URL" : "URL"} grow minWidth={320}>
              <Input value={url} placeholder="https://hooks.slack.com/services/…" autoComplete="off" spellCheck={false} onChange={(event) => setUrl(event.target.value)} />
              <div className="alr-hint">A Slack incoming webhook, or any https address that accepts a POST.</div>
            </Field>
            <Field label="Secret (optional)" minWidth={240}>
              <Input type="password" value={secret} autoComplete="new-password" placeholder="any text you choose" onChange={(event) => setSecret(event.target.value)} />
              <div className="alr-hint">Signs every request so your server can check it came from Pinecall. Never shown again.</div>
            </Field>
          </div>
          <Button kind="primary" size="md" type="submit" disabled={busy || url.trim() === ""}>
            {busy ? "Saving…" : webhook ? "Replace" : "Connect"}
          </Button>
          {webhook === null && <span className="alr-hint">Until you connect one, alerts show only in the bell and on the agents' logs.</span>}
        </form>
      </Card>

      <Card>
        <CardHead title="What sends an alert" />
        <div className="alr-rows">
          {POSTED.map((one) => (
            <KV key={one.type} keyWidth={150} label={one.name}>
              {one.when} <code className="alr-type">{one.type}</code>
            </KV>
          ))}
        </div>
      </Card>

      <Card>
        <CardHead
          title="What your server receives"
          meta="a POST with a JSON body; if it fails, Pinecall tries once more within five seconds"
          action={<TextAction onClick={() => setExample(!example)}>{example ? "Hide example" : "Show example"}</TextAction>}
        />
        {example && <pre className="alr-post">{A_POST}</pre>}
      </Card>

      <Refused>{refused}</Refused>
    </Page>
  );
}
