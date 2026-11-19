/** Email: a mailbox of the org's connected once (IMAP to read it, SMTP to answer from it) and its address given to an agent; or its server changed. */

import { useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Field } from "../ui/setting";
import { addNumber, bringCarrier, type Carrier } from "./door";
import { AgentField, type Mover } from "./parts";
import { Submit, type WayProps } from "./ways";
import "../calls/email.css";

// A field of the form, with its label and what it shows before anything is typed.
function Input({ label, value, onChange, hint, secret = false, required = false, locked = false }: { label: string; value: string; onChange: (value: string) => void; hint?: string | undefined; secret?: boolean; required?: boolean; locked?: boolean }): ReactNode {
  return (
    <Field label={label}>
      <input
        className="cfg-input"
        aria-label={label}
        type={secret ? "password" : "text"}
        placeholder={hint}
        required={required}
        readOnly={locked}
        spellCheck={false}
        autoComplete={secret ? "new-password" : "off"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

const portOf = (written: string, fallback: number): number => (/^\d+$/.test(written.trim()) ? Number(written.trim()) : fallback);
const setting = (carrier: Carrier | undefined, name: string): string => String(carrier?.settings[name] ?? "");

/** The mailbox's fields: empty to connect one, its own to change its server, its passwords left empty to keep them. */
export function MailboxForm({ editing, mover, onSaved, agentField }: { editing?: Carrier | undefined; mover: Mover; onSaved: (address: string) => Promise<void>; agentField?: ReactNode }): ReactNode {
  const credentials = useCredentials();
  const [address, setAddress] = useState(editing?.account ?? "");
  const [password, setPassword] = useState("");
  const [imapHost, setImapHost] = useState(setting(editing, "imap_host"));
  const [imapPort, setImapPort] = useState(setting(editing, "imap_port") || "993");
  const [smtpHost, setSmtpHost] = useState(setting(editing, "smtp_host"));
  const [smtpPort, setSmtpPort] = useState(setting(editing, "smtp_port") || "465");
  const [relayUser, setRelayUser] = useState(setting(editing, "smtp_username"));
  const [relayPassword, setRelayPassword] = useState("");
  const [name, setName] = useState(setting(editing, "sender_name"));
  const domain = address.includes("@") ? address.split("@")[1] : "";
  const keeps = editing === undefined ? undefined : "Leave it empty to keep the one it has";
  const save = (event: FormEvent): void => {
    event.preventDefault();
    const mailbox = address.trim().toLowerCase();
    const relay = relayUser.trim() === "" ? {} : { smtp_username: relayUser.trim(), ...(relayPassword === "" ? {} : { smtp_password: relayPassword }) };
    void mover
      .move(() =>
        bringCarrier(credentials, {
          kind: "email",
          address: mailbox,
          ...(password === "" ? {} : { password }),
          imap_host: imapHost.trim() || `mail.${domain}`,
          imap_port: portOf(imapPort, 993),
          smtp_host: smtpHost.trim() || imapHost.trim() || `mail.${domain}`,
          smtp_port: portOf(smtpPort, 465),
          ...relay,
          ...(name.trim() === "" ? {} : { sender_name: name.trim() }),
        }),
      )
      .then(() => onSaved(mailbox), () => undefined);
  };
  return (
    <form className="num-form" onSubmit={save}>
      <p className="num-hint">
        {editing === undefined
          ? "Connect the mailbox once. Both logins are checked with its server, kept encrypted, and never shown again. Only emails that arrive from now on are answered."
          : "Both logins are checked again before anything changes. A password left empty keeps the one it has."}
      </p>
      <Input label="Address" value={address} onChange={setAddress} hint="help@yourcompany.com" required locked={editing !== undefined} />
      <Input label="Password" value={password} onChange={setPassword} hint={keeps ?? "The mailbox's own, for IMAP"} secret required={editing === undefined} />
      <div className="mail-ports">
        <Input label="IMAP server" value={imapHost} onChange={setImapHost} hint={domain === "" ? "mail.yourcompany.com" : `mail.${domain}`} />
        <Input label="Port" value={imapPort} onChange={setImapPort} hint="993" />
      </div>
      <div className="mail-ports">
        <Input label="SMTP server" value={smtpHost} onChange={setSmtpHost} hint="The same, or a relay: email-smtp.us-east-1.amazonaws.com" />
        <Input label="Port" value={smtpPort} onChange={setSmtpPort} hint="465, or 587" />
      </div>
      <Input label="Relay login" value={relayUser} onChange={setRelayUser} hint="Optional: a relay's own (Amazon SES), else the mailbox's" />
      {relayUser.trim() !== "" && <Input label="Relay password" value={relayPassword} onChange={setRelayPassword} hint={keeps} secret />}
      <Input label="Name the contact reads" value={name} onChange={setName} hint="Optional: Your Company Support" />
      {agentField}
      <Submit busy={mover.busy} doing={editing === undefined ? "Connecting…" : "Checking…"} disabled={address.trim() === "" || (editing === undefined && password === "")}>
        {editing === undefined ? "Connect the mailbox" : "Save the server"}
      </Submit>
    </form>
  );
}

/** Add a number ▸ Email: the mailbox connected, then its address answers email for the agent. */
export function EmailWay({ agents, agent: fixed, mover, onAccount, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const connected = async (mailbox: string): Promise<void> => {
    await onAccount();
    await mover.move(() => addNumber(credentials, { number: mailbox, agent, channel: "email", account: mailbox }, false));
    onAdded(mailbox, <p className="num-hint">Emails written to it from now on are answered within a minute, set in the org&apos;s template.</p>);
  };
  return <MailboxForm mover={mover} onSaved={connected} agentField={<AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />} />;
}
