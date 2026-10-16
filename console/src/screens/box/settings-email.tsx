/** Email: the mail server the box sends invitations and password resets through, and one letter to prove it. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, KV, Pill, Refused, Select, SelectItem, TextAction } from "../../ui";
import { readMail, removeMail, saveMail, SECURITIES, testMail, type Mail, type Security } from "./door-settings";
import { NoSuchDoor } from "./settings";
import { useDoor, useMove } from "./use-door";

/**
 * The tab. Any SMTP server: Amazon SES, Postmark, a company's own. An org's own account, where it
 * has one, wins over this; what is saved here wins over the box's environment.
 */
export function SettingsEmail(): ReactNode {
  const credentials = useCredentials();
  const mail = useDoor(useCallback(() => readMail(credentials), [credentials]));
  const acting = useMove();
  const [editing, setEditing] = useState(false);
  const [to, setTo] = useState("");
  const [tested, setTested] = useState<{ sent: boolean; error: string | null } | null>(null);

  if (mail.value === undefined) return <Refused>{mail.refused}</Refused>;
  if (mail.value === null) return <NoSuchDoor />;
  const kept = mail.value;

  const test = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setTested(null);
    await acting.move(async () => {
      setTested(await testMail(credentials, to.trim()));
      await mail.reread();
    });
  };

  return (
    <>
      <Refused>{acting.refused}</Refused>
      <Card>
        <CardHead title="The box's mail" meta="invitations, password resets and a forgotten password">
          <span className="box-head-moves">
            <Pill tone={kept.configured ? "green" : "gray"}>{kept.configured ? (kept.source === "environment" ? "on · from the environment" : "on") : "off"}</Pill>
          </span>
        </CardHead>

        {editing || !kept.configured ? (
          <MailForm
            kept={kept}
            busy={acting.busy}
            onCancel={kept.configured ? () => setEditing(false) : undefined}
            onSave={async (wanted) => {
              const saved = await acting.move(async () => {
                await saveMail(credentials, wanted);
                await mail.reread();
              });
              if (saved) setEditing(false);
            }}
          />
        ) : (
          <div className="box-kvs">
            <KV label="Server" keyWidth={120}>
              <span className="box-fixed">{`${kept.host ?? "—"}:${kept.port ?? ""}`}</span> · {kept.security ?? "starttls"}
            </KV>
            <KV label="Username" keyWidth={120}>
              <span className="box-fixed">{kept.username ?? "none"}</span>
            </KV>
            <KV label="From" keyWidth={120}>
              {kept.from ?? "—"}
            </KV>
            <KV label="Last letter" keyWidth={120}>
              {kept.last_error ? <span className="box-bad">{kept.last_error}</span> : kept.verified_at ? `went through · ${kept.verified_at.slice(0, 16).replace("T", " ")}` : "none sent yet"}
            </KV>
            <div className="box-line box-kvs-moves">
              <Button size="sm" onClick={() => setEditing(true)}>
                {kept.source === "environment" ? "Replace it here" : "Change"}
              </Button>
              {kept.source !== "environment" && (
                <TextAction
                  danger
                  disabled={acting.busy}
                  onClick={() =>
                    void acting.move(async () => {
                      await removeMail(credentials);
                      await mail.reread();
                    })
                  }
                >
                  Forget it
                </TextAction>
              )}
            </div>
          </div>
        )}
      </Card>

      {kept.configured && (
        <Card>
          <CardHead title="Send a test letter" meta="the one door that waits for the mail server's answer" />
          <div className="ui-card-body">
            <form className="ui-form" onSubmit={(event) => void test(event)}>
              <Field label="To" grow minWidth={240}>
                <Input type="email" value={to} placeholder="you@company.com" onChange={(event) => setTo(event.target.value)} required />
              </Field>
              <Button size="form" type="submit" disabled={acting.busy}>
                {acting.busy ? "Sending…" : "Send"}
              </Button>
            </form>
            {tested !== null && (tested.sent ? <div className="box-done box-done-under">Taken by the mail server.</div> : <div className="box-bad box-note">{tested.error ?? "It was refused."}</div>)}
          </div>
        </Card>
      )}
    </>
  );
}

function MailForm({
  kept,
  busy,
  onSave,
  onCancel,
}: {
  kept: Mail;
  busy: boolean;
  onSave: (wanted: Parameters<typeof saveMail>[1]) => Promise<void>;
  onCancel?: (() => void) | undefined;
}): ReactNode {
  const [host, setHost] = useState(kept.host ?? "");
  const [port, setPort] = useState(String(kept.port ?? 587));
  const [security, setSecurity] = useState<Security>(SECURITIES.find((one) => one === kept.security) ?? "starttls");
  const [username, setUsername] = useState(kept.username ?? "");
  const [password, setPassword] = useState("");
  const [from, setFrom] = useState(kept.from ?? "");

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    void onSave({
      host: host.trim(),
      port: Number(port),
      security,
      username: username.trim() === "" ? null : username.trim(),
      // Left empty on a change, the gateway keeps the password it has.
      ...(password === "" ? {} : { password }),
      from: from.trim(),
    });
  };

  return (
    <form className="box-form" onSubmit={submit}>
      <div className="box-form-grid">
        <Field label="Host">
          <Input value={host} placeholder="email-smtp.us-east-1.amazonaws.com" onChange={(event) => setHost(event.target.value)} required />
        </Field>
        <div className="box-form-pair">
          <Field label="Port">
            <Input inputMode="numeric" value={port} onChange={(event) => setPort(event.target.value.replace(/[^0-9]/g, ""))} required />
          </Field>
          <Field label="Security">
            <Select value={security} onValueChange={(value) => setSecurity(value as Security)}>
              {SECURITIES.map((one) => (
                <SelectItem key={one} value={one}>
                  {one}
                </SelectItem>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Username">
          <Input autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)} />
        </Field>
        <Field label="Password, sent once">
          <Input type="password" autoComplete="new-password" value={password} placeholder={kept.configured ? "unchanged" : "never shown again"} onChange={(event) => setPassword(event.target.value)} />
        </Field>
        <Field label="From">
          <Input value={from} placeholder="Pinecall <noreply@pinecall.io>" onChange={(event) => setFrom(event.target.value)} required />
        </Field>
      </div>
      <div className="box-line">
        <Button kind="primary" size="md" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </Button>
        {onCancel !== undefined && <TextAction onClick={onCancel}>Cancel</TextAction>}
        <span className="ui-note">Saving sends nothing: the test letter below is what proves it.</span>
      </div>
    </form>
  );
}
