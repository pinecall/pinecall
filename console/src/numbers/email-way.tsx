/** Email: a mailbox of the org's connected once (IMAP to read it, SMTP to answer from it) and its address given to an agent. */

import { useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Field } from "../ui/setting";
import { addNumber, bringCarrier } from "./door";
import { AgentField } from "./parts";
import { Submit, type WayProps } from "./ways";

// A field of the form, with its label and what it shows before anything is typed.
function Input({ label, value, onChange, hint, secret = false, required = false }: { label: string; value: string; onChange: (value: string) => void; hint?: string; secret?: boolean; required?: boolean }): ReactNode {
  return (
    <Field label={label}>
      <input
        className="cfg-input"
        aria-label={label}
        type={secret ? "password" : "text"}
        placeholder={hint}
        required={required}
        spellCheck={false}
        autoComplete={secret ? "new-password" : "off"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

const portOf = (written: string, fallback: number): number => (/^\d+$/.test(written.trim()) ? Number(written.trim()) : fallback);

/** The mailbox is checked with its server as it is connected (both logins), kept encrypted, and its address answers email for the agent. */
export function EmailWay({ agents, agent: fixed, mover, onAccount, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState("993");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("465");
  const [relayUser, setRelayUser] = useState("");
  const [relayPassword, setRelayPassword] = useState("");
  const [name, setName] = useState("");
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const domain = address.includes("@") ? address.split("@")[1] : "";
  const connect = (event: FormEvent): void => {
    event.preventDefault();
    const mailbox = address.trim().toLowerCase();
    const relay = relayUser.trim() === "" ? {} : { smtp_username: relayUser.trim(), ...(relayPassword === "" ? {} : { smtp_password: relayPassword }) };
    void mover
      .move(async () => {
        await bringCarrier(credentials, {
          kind: "email",
          address: mailbox,
          password,
          imap_host: imapHost.trim() || `mail.${domain}`,
          imap_port: portOf(imapPort, 993),
          smtp_host: smtpHost.trim() || imapHost.trim() || `mail.${domain}`,
          smtp_port: portOf(smtpPort, 465),
          ...relay,
          ...(name.trim() === "" ? {} : { sender_name: name.trim() }),
        });
        await onAccount();
        await addNumber(credentials, { number: mailbox, agent, channel: "email", account: mailbox }, false);
      })
      .then(() => onAdded(mailbox, <p className="num-hint">Emails written to it from now on are answered within a minute, set in the org&apos;s layout.</p>), () => undefined);
  };
  return (
    <form className="num-form" onSubmit={connect}>
      <p className="num-hint">Connect the mailbox once. Both logins are checked with its server, kept encrypted, and never shown again. Only emails that arrive from now on are answered.</p>
      <Input label="Address" value={address} onChange={setAddress} hint="help@yourcompany.com" required />
      <Input label="Password" value={password} onChange={setPassword} hint="The mailbox's own, for IMAP" secret required />
      <Input label="IMAP server" value={imapHost} onChange={setImapHost} hint={domain === "" ? "mail.yourcompany.com" : `mail.${domain}`} />
      <Input label="IMAP port" value={imapPort} onChange={setImapPort} hint="993" />
      <Input label="SMTP server" value={smtpHost} onChange={setSmtpHost} hint="The same, or a relay: email-smtp.us-east-1.amazonaws.com" />
      <Input label="SMTP port" value={smtpPort} onChange={setSmtpPort} hint="465, or 587 for STARTTLS" />
      <Input label="Relay login" value={relayUser} onChange={setRelayUser} hint="Optional: a relay's own (Amazon SES), else the mailbox's" />
      {relayUser.trim() !== "" && <Input label="Relay password" value={relayPassword} onChange={setRelayPassword} secret />}
      <Input label="Name the contact reads" value={name} onChange={setName} hint="Optional: Your Company Support" />
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <Submit busy={mover.busy} doing="Connecting…" disabled={address.trim() === "" || password === "" || agent === ""}>
        Connect the mailbox
      </Submit>
    </form>
  );
}
