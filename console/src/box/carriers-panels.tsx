/** What Carriers opens beside it and its two settings: one carrier in full, the account numbers are bought on, and the test line. */

import { useCallback, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { useMove } from "../numbers/parts";
import { shown } from "../numbers/words";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { dropNumbersAccount, readBoxNumbers, readNumbersAccount, readTestLine, saveNumbersAccount, saveTestLine, type BoxNumber, type CatalogCarrier, type NumbersAccount } from "./telephony-door";
import { Head, OrgLink, useDoor } from "./telephony-parts";

export function CarrierPanel({ carrier, onClose }: { carrier: CatalogCarrier; onClose: () => void }): ReactNode {
  return (
    <SidePanel
      title={carrier.name}
      icon="numbers"
      about={carrier.control ? `Pinecall talks to ${carrier.name} for the organization: it lists the account's numbers, points the one picked here, and can dial out.` : `An organization pastes one address in ${carrier.name}'s portal, and its calls come here. Pinecall never touches the ${carrier.name} account.`}
      onClose={onClose}
    >
      <dl className="tst-facts">
        <div>
          <dt>Standing</dt>
          <dd>{carrier.fixed ? "Always on: it is this deployment's own carrier" : carrier.admitted ? "Admitted: organizations can bring numbers from it" : "Not admitted: no organization is offered it"}</dd>
        </div>
        <div>
          <dt>Numbers</dt>
          <dd>{carrier.numbers === 0 ? "None come through it" : `${carrier.numbers} across every organization`}</dd>
        </div>
        <div>
          <dt>List read on</dt>
          <dd>{carrier.read_on}</dd>
        </div>
        <div>
          <dt>Read from</dt>
          <dd>
            <a className="tst-link" href={carrier.source} target="_blank" rel="noreferrer">
              {carrier.source}
            </a>
          </dd>
        </div>
      </dl>
      <Field label="Where its calls come from">
        <p className="dash-quiet">The networks {carrier.name} publishes. While it is admitted, calls from these are let in.</p>
        <div className="tel-nets">
          {carrier.networks.map((network) => (
            <code key={network} className="tel-mono">
              {network}
            </code>
          ))}
        </div>
      </Field>
    </SidePanel>
  );
}

function AccountPanel({ standing, onKept, onClose }: { standing: NumbersAccount | null; onKept: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [sid, setSid] = useState(standing?.account_sid ?? "");
  const [user, setUser] = useState("");
  const [secret, setSecret] = useState("");
  const [label, setLabel] = useState(standing?.label ?? "");
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const save = (): void => {
    if (sid.trim() === "" || secret === "") return setRefused("The account SID and its secret are both needed.");
    setSaving(true);
    setRefused(null);
    saveNumbersAccount(credentials, { account_sid: sid.trim(), user: user.trim() || sid.trim(), secret, label: label.trim() })
      .then(() => (onKept(), onClose()), (failed: unknown) => setRefused(saidBy(failed)))
      .finally(() => setSaving(false));
  };

  return (
    <EditDialog title="Twilio account for buying numbers" icon="coins" about="Every number an organization buys is bought on this account, and billed by Twilio to it. It is tried with Twilio before it is kept. The secret is stored encrypted and never shown again." saving={saving} refused={refused} onSave={save} onClose={onClose}>
      <Field label="Account SID">
        <input className="cfg-input" aria-label="Account SID" placeholder="AC…" autoFocus autoComplete="off" value={sid} onChange={(event) => setSid(event.target.value)} />
      </Field>
      <Field label="API key SID">
        <input className="cfg-input" aria-label="API key SID" placeholder="SK…, optional" autoComplete="off" value={user} onChange={(event) => setUser(event.target.value)} />
        <span className="dash-quiet">Leave it empty to sign in with the account's own auth token.</span>
      </Field>
      <Field label={user.trim() === "" ? "Auth token" : "API key secret"}>
        <input className="cfg-input" type="password" aria-label="Secret" placeholder="Paste it" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} />
      </Field>
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="Pinecall numbers, optional" value={label} onChange={(event) => setLabel(event.target.value)} />
      </Field>
    </EditDialog>
  );
}

export function NumbersAccountSection(): ReactNode {
  const credentials = useCredentials();
  const account = useDoor(useCallback(async () => ({ held: await readNumbersAccount(credentials) }), [credentials]));
  const mover = useMove();
  const [editing, setEditing] = useState(false);
  const stop = useCallback(() => setEditing(false), []);
  const held = account.value?.held ?? null;
  const refused = account.refused ?? mover.refused;

  return (
    <section className="tst-list" aria-label="Account numbers are bought on">
      <Head icon="coins" title="Account numbers are bought on" about="The Twilio account behind Buy a number. Without one, organizations can still bring their own numbers but cannot buy any.">
        {account.value !== null && (
          <button type="button" className="cfg-save tst-action" onClick={() => setEditing(true)}>
            {held === null && <Icon name="plus" size={12} />}
            {held === null ? "Connect account" : "Replace"}
          </button>
        )}
      </Head>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      {account.value === null && account.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
      {account.value !== null && held === null && <p className="dash-quiet tst-none">No account connected. Nobody can buy a number here.</p>}
      {held !== null && (
        <>
          <div className="tst-row tel-row">
            <span className="tst-row-words">
              <span className="tst-row-name">{held.label == null || held.label === "" ? "Twilio account" : held.label}</span>
              <span className="tst-row-under">
                <code className="tel-mono">{held.account_sid}</code>
              </span>
            </span>
            <span className="tst-status tst-status-held tel-status">Selling</span>
            <ConfirmButton label="Forget" asks="Stop selling numbers?" danger onConfirm={() => void mover.move(() => dropNumbersAccount(credentials)).then(account.reread, () => undefined)} />
          </div>
          <p className="dash-quiet tel-note">Forgetting it stops new purchases. Numbers already bought keep ringing. Its secret is never shown: to change it, replace the account.</p>
        </>
      )}
      {editing && <AccountPanel standing={held} onKept={account.reread} onClose={stop} />}
    </section>
  );
}

function TestLinePanel({ standing, numbers, onKept, onClose }: { standing: string | null; numbers: readonly BoxNumber[]; onKept: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [picked, setPicked] = useState(standing ?? "");
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const save = (): void => {
    if (picked === "") return setRefused("Pick a number first.");
    setSaving(true);
    setRefused(null);
    saveTestLine(credentials, picked)
      .then(() => (onKept(), onClose()), (failed: unknown) => setRefused(saidBy(failed)))
      .finally(() => setSaving(false));
  };

  return (
    <EditDialog title="Test line" icon="numbers" about="From the next call, a person calling this number from the mobile they registered reaches their own sandbox agent. Anyone else still gets the number's own agent." saving={saving} refused={refused} onSave={save} onClose={onClose}>
      <Field label="Number">
        {numbers.length === 0 ? (
          <p className="dash-quiet">No phone number is routed in the sandbox yet. Add one to an organization's sandbox first.</p>
        ) : (
          <Select label="Test line number" placeholder="Pick a sandbox number" items={numbers.map((one) => ({ value: one.number, label: shown(one.number), detail: `${one.org}, answered by ${one.agent}` }))} value={picked} onChange={setPicked} />
        )}
        <span className="dash-quiet">Only numbers answered in the sandbox can be the test line.</span>
      </Field>
    </EditDialog>
  );
}

export function TestLineSection(): ReactNode {
  const credentials = useCredentials();
  const line = useDoor(useCallback(async () => ({ number: await readTestLine(credentials) }), [credentials]));
  const numbers = useDoor(useCallback(() => readBoxNumbers(credentials), [credentials]));
  const mover = useMove();
  const [editing, setEditing] = useState(false);
  const stop = useCallback(() => setEditing(false), []);
  const number = line.value?.number ?? null;
  const row = (numbers.value ?? []).find((one) => one.number === number && one.env === "sandbox");
  const refused = line.refused ?? mover.refused;

  return (
    <section className="tst-list" aria-label="Test line">
      <Head icon="simulations" title="Test line" about="One sandbox number that people call from their own mobile to talk to the agent they are building, without buying a number.">
        {line.value !== null && (
          <button type="button" className="cfg-save tst-action" onClick={() => setEditing(true)}>
            {number === null ? "Choose a number" : "Change"}
          </button>
        )}
      </Head>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      {line.value === null && line.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
      {line.value !== null && number === null && <p className="dash-quiet tst-none">No test line. People cannot test by calling from their mobile.</p>}
      {number !== null && (
        <>
          <div className="tst-row tel-row">
            <span className="tst-row-words">
              <span className="tst-row-name">{shown(number)}</span>
              <span className="tst-row-under">
                {row === undefined ? (
                  "Callers who registered their mobile reach their own agent."
                ) : (
                  <>
                    A number of <OrgLink slug={row.org} />. Anyone who did not register their mobile gets {row.agent}.
                  </>
                )}
              </span>
            </span>
            <span className="tst-status tst-status-held tel-status">In use</span>
            <ConfirmButton label="Forget" asks="Stop the test line?" danger onConfirm={() => void mover.move(() => saveTestLine(credentials, null)).then(line.reread, () => undefined)} />
          </div>
          <p className="dash-quiet tel-note">Forgetting it ends testing from a mobile for everyone. The number itself keeps ringing its own agent.</p>
        </>
      )}
      {editing && <TestLinePanel standing={number} numbers={(numbers.value ?? []).filter((one) => one.env === "sandbox" && one.channel === "phone")} onKept={line.reread} onClose={stop} />}
    </section>
  );
}
