/** Email: the mailbox the deployment's letters go through, set, proved with one real letter, and removed; its password is never shown back. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { ago } from "../lib/format";
import { useMove } from "../numbers/parts";
import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { readMail, removeMail, saveMail, SECURITIES, testMail, type Mail, type Security } from "./settings-door";
import { Effect, NoSuchDoor, Refusal, Section, useDoor } from "./settings-parts";

const SECURITY_ITEMS = [
  { value: "starttls", label: "STARTTLS", detail: "The usual, on port 587." },
  { value: "tls", label: "TLS", detail: "Encrypted from the first byte, on port 465." },
  { value: "none", label: "None", detail: "Unencrypted. Only for a server on the same private network." },
];

function MailPanel({ was, onKept, onClose }: { was: Mail; onKept: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const acting = useMove();
  const [host, setHost] = useState(was.host ?? "");
  const [port, setPort] = useState(String(was.port ?? 587));
  const [security, setSecurity] = useState<Security>(SECURITIES.find((one) => one === was.security) ?? "starttls");
  const [username, setUsername] = useState(was.username ?? "");
  const [password, setPassword] = useState("");
  const [from, setFrom] = useState(was.from ?? "");
  const [missing, setMissing] = useState(false);
  // A mailbox from the environment has no stored password to keep: the first save here needs one typed.
  const keeps = was.configured && was.source === "stored";
  const save = (): void => {
    if (host.trim() === "" || port === "" || from.trim() === "") return setMissing(true);
    setMissing(false);
    const wanted = { host: host.trim(), port: Number(port), security, username: username.trim() === "" ? null : username.trim(), from: from.trim(), ...(password === "" ? {} : { password }) };
    void acting.move(async () => (await saveMail(credentials, wanted), await onKept())).then(onClose, () => undefined);
  };
  return (
    <EditDialog title="Mailbox" icon="mail" about="Any mail server that speaks SMTP: Amazon SES, Postmark, your company's own." saving={acting.busy} refused={missing ? "Type the server, its port and the From address." : acting.refused} onSave={save} onClose={onClose}>
      <Effect>Every invitation, password reset and sign-up confirmation goes out through it from the next one. Saving sends nothing: send a test after.</Effect>
      <Field label="Server">
        <input className="cfg-input" aria-label="Server" placeholder="email-smtp.us-east-1.amazonaws.com" spellCheck={false} autoComplete="off" value={host} onChange={(event) => setHost(event.target.value)} />
      </Field>
      <div className="bxs-pair">
        <Field label="Port">
          <input className="cfg-input" inputMode="numeric" aria-label="Port" value={port} onChange={(event) => setPort(event.target.value.replace(/[^0-9]/g, ""))} />
        </Field>
        <Field label="Encryption">
          <Select items={SECURITY_ITEMS} value={security} label="Encryption" searchable={false} onChange={(picked) => setSecurity(picked as Security)} />
        </Field>
      </div>
      <Field label="Username">
        <input className="cfg-input" aria-label="Username" spellCheck={false} autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)} />
      </Field>
      <Field label="Password">
        <input className="cfg-input" type="password" aria-label="Password" placeholder={keeps ? "Unchanged. Type one to replace it" : "Kept encrypted, never shown again"} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </Field>
      <Field label="From">
        <input className="cfg-input" aria-label="From" placeholder="Acme <no-reply@acme.example>" spellCheck={false} value={from} onChange={(event) => setFrom(event.target.value)} />
        <p className="dash-quiet">The name and address people see the letters come from.</p>
      </Field>
    </EditDialog>
  );
}

function TestPanel({ onSent, onClose }: { onSent: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const acting = useMove();
  const [to, setTo] = useState("");
  const [tested, setTested] = useState<{ sent: boolean; error: string | null } | null>(null);
  const send = (event: FormEvent): void => {
    event.preventDefault();
    setTested(null);
    void acting.move(async () => (setTested(await testMail(credentials, to.trim())), await onSent())).catch(() => undefined);
  };
  return (
    <SidePanel
      title="Send a test letter"
      icon="mail"
      about="One real letter through the mailbox, waited for. It is the only way to know the mailbox works."
      onClose={onClose}
      footer={
        <>
          <Refusal>{acting.refused}</Refusal>
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Close
            </button>
            <button type="submit" form="bxs-test-letter" className="cfg-save" disabled={acting.busy || to.trim() === ""}>
              {acting.busy ? "Sending…" : "Send"}
            </button>
          </div>
        </>
      }
    >
      <form id="bxs-test-letter" className="cfg-dialog-body" onSubmit={send}>
        <Field label="To">
          <input className="cfg-input" type="email" aria-label="To" placeholder="you@company.com" autoFocus value={to} onChange={(event) => setTo(event.target.value)} />
        </Field>
        {tested !== null && (tested.sent ? <p className="bxs-good">The mail server took it. Check that inbox.</p> : <Refusal>{tested.error ?? "The mail server refused it."}</Refusal>)}
      </form>
    </SidePanel>
  );
}

function standingOf(mail: Mail): { mood: "held" | "broke" | "waiting"; said: string } {
  if (mail.last_error != null && mail.last_error !== "") return { mood: "broke", said: "Last letter failed" };
  if (mail.verified_at != null) return { mood: "held", said: "Working" };
  return { mood: "waiting", said: "Not tried yet" };
}

export function SettingsEmail(): ReactNode {
  const credentials = useCredentials();
  const mail = useDoor(useCallback(() => readMail(credentials), [credentials]));
  const acting = useMove();
  const [open, setOpen] = useState<"edit" | "test" | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const kept = mail.value;
  const fromEnvironment = kept?.source === "environment";
  const remove = (): void => void acting.move(async () => (await removeMail(credentials), await mail.reread())).catch(() => undefined);
  const standing = kept == null ? null : standingOf(kept);

  return (
    <>
      <Refusal>{mail.refused ?? acting.refused}</Refusal>
      <Section
        icon="mail"
        title="Mailbox"
        about="The letters of the whole deployment go out through it: invitations, password resets, sign-up confirmations. An organization with a mailbox of its own uses that instead."
        action={
          kept != null && (
            <button type="button" className="cfg-save tst-action" onClick={() => setOpen("edit")}>
              {!kept.configured ? "Set up" : fromEnvironment ? "Replace it here" : "Change"}
            </button>
          )
        }
      >
        {kept === undefined && mail.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {kept === null && <NoSuchDoor />}
        {kept != null && !kept.configured && <p className="dash-quiet tst-none">No mailbox. Nothing is sent: an invited person gets no letter, and nobody can reset a password.</p>}
        {kept != null && kept.configured && standing !== null && (
          <>
            <div className="tst-row bxs-row">
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <span className="dash-clip">{kept.from ?? "No From address"}</span>
                  {fromEnvironment && <span className="tst-tag">set at install</span>}
                </span>
                <span className="tst-row-under dash-clip">
                  Through {kept.host ?? "—"}
                  {kept.port == null ? "" : `, port ${kept.port}`}. Its password is kept and never shown.
                </span>
              </span>
              {kept.verified_at != null && <span className="tst-row-when">Last letter {ago(Date.parse(kept.verified_at) / 1000)}</span>}
              <span className={`tst-status bxs-status tst-status-${standing.mood}`}>{standing.said}</span>
              <span className="bxs-acts">
                <button type="button" className="app-button" onClick={() => setOpen("test")}>
                  Send a test
                </button>
                {!fromEnvironment && <ConfirmButton label="Remove" asks="Stop sending letters?" danger onConfirm={remove} />}
              </span>
            </div>
            {kept.last_error != null && kept.last_error !== "" && <p className="cfg-refused tst-none">The mail server said: {kept.last_error}</p>}
            {fromEnvironment && <p className="dash-quiet tst-none">This mailbox came with the installation. One saved here is used instead; removing that one brings this back.</p>}
          </>
        )}
      </Section>
      {open === "edit" && kept != null && <MailPanel was={kept} onKept={mail.reread} onClose={close} />}
      {open === "test" && <TestPanel onSent={mail.reread} onClose={close} />}
    </>
  );
}
