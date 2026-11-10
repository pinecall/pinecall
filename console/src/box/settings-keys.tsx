/** Provider keys: the vendors the deployment holds a key for, added, replaced and removed, and the Twilio account its organizations' numbers are bought on. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { brandOf } from "../configure/vendors";
import { useMove } from "../numbers/parts";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { Field, Mark } from "../ui/setting";
import { dropBoxKey, dropNumbersAccount, keepBoxKey, readCatalogue, readHeldVendors, readNumbersAccount, saveNumbersAccount, type Catalogue } from "./settings-door";
import { Effect, Refusal, Section, useDoor } from "./settings-parts";

const STAGE_NAMES: Record<string, string> = { stt: "Transcriber", llm: "Model", tts: "Voice", realtime: "Realtime" };

function doesSaid(catalogue: Catalogue | undefined, vendor: string): string {
  const does = catalogue?.providers.find((one) => one.name === vendor)?.does ?? [];
  return does.length === 0 ? "A key this deployment uses itself" : does.map((stage) => STAGE_NAMES[stage] ?? stage).join(", ");
}

/** `vendor` given, its key is replaced; null, the vendor is picked among every one this runtime has. */
function KeyPanel({ vendor, held, catalogue, onKept, onClose }: { vendor: string | null; held: readonly string[]; catalogue: Catalogue | undefined; onKept: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const acting = useMove();
  const [picked, setPicked] = useState(vendor ?? "");
  const [key, setKey] = useState("");
  const [missing, setMissing] = useState(false);
  const replaces = held.includes(picked);
  const items = [...new Set([...(catalogue?.providers.map((one) => one.name) ?? []), ...held])]
    .sort((one, other) => brandOf(one).localeCompare(brandOf(other)))
    .map((name) => ({ value: name, label: brandOf(name), detail: held.includes(name) ? "Has a key: this replaces it" : doesSaid(catalogue, name), keywords: name, leading: <Mark letter={brandOf(name).charAt(0)} /> }));
  const save = (): void => {
    if (picked === "" || key.trim() === "") return setMissing(true);
    setMissing(false);
    void acting.move(async () => (await keepBoxKey(credentials, picked, key.trim()), await onKept())).then(onClose, () => undefined);
  };
  return (
    <EditDialog title={vendor === null ? "Add a provider key" : `Replace the ${brandOf(vendor)} key`} icon="brain" about="Kept encrypted and never shown again, to anyone." saving={acting.busy} refused={missing ? "Pick the vendor and paste its key." : acting.refused} onSave={save} onClose={onClose}>
      <Effect>
        {replaces
          ? `Every call that runs on this deployment's ${brandOf(picked)} key uses the new one from the next call. ${brandOf(picked)} bills the account the new key belongs to.`
          : "Holding a key is offering the vendor: an organization lent it runs on your account, and the vendor bills you. Who is lent it is set in Admission for new organizations, and on each organization."}
      </Effect>
      {vendor === null && (
        <Field label="Vendor">
          <Select items={items} value={picked} label="Vendor" placeholder="Choose a vendor" searchPlaceholder="Search vendors" onChange={setPicked} />
        </Field>
      )}
      <Field label="API key">
        <input className="cfg-input" type="password" aria-label="API key" placeholder={picked === "" ? "Paste the key" : `Paste the ${brandOf(picked)} API key`} autoComplete="new-password" value={key} onChange={(event) => setKey(event.target.value)} />
      </Field>
    </EditDialog>
  );
}

function NumbersPanel({ replaces, onKept, onClose }: { replaces: boolean; onKept: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const acting = useMove();
  const [sid, setSid] = useState("");
  const [user, setUser] = useState("");
  const [secret, setSecret] = useState("");
  const [label, setLabel] = useState("");
  const [missing, setMissing] = useState(false);
  const save = (): void => {
    if (sid.trim() === "" || secret === "") return setMissing(true);
    setMissing(false);
    void acting.move(async () => (await saveNumbersAccount(credentials, { account_sid: sid.trim(), user: user.trim() || sid.trim(), secret, label: label.trim() }), await onKept())).then(onClose, () => undefined);
  };
  return (
    <EditDialog title="Twilio account" icon="numbers" about="Checked with Twilio before it is kept. Its secret is encrypted and never shown again." saving={acting.busy} refused={missing ? "Type the account SID and the secret." : acting.refused} onSave={save} onClose={onClose}>
      <Effect>{replaces ? "Numbers bought from now on are bought on the new account, and Twilio bills it. Numbers already bought stay on the old one and keep ringing." : "Organizations can buy phone numbers here. Each is bought on this account, Twilio bills you, and it counts against the organization's phone numbers limit."}</Effect>
      <Field label="Account SID">
        <input className="cfg-input" aria-label="Account SID" placeholder="AC…" spellCheck={false} autoComplete="off" value={sid} onChange={(event) => setSid(event.target.value)} />
      </Field>
      <Field label="API key SID">
        <input className="cfg-input" aria-label="API key SID" placeholder="SK…  Empty uses the account SID" spellCheck={false} autoComplete="off" value={user} onChange={(event) => setUser(event.target.value)} />
      </Field>
      <Field label="Secret">
        <input className="cfg-input" type="password" aria-label="Secret" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} />
      </Field>
      <Field label="Name, if you want one">
        <input className="cfg-input" aria-label="Name" placeholder="Main account" autoComplete="off" value={label} onChange={(event) => setLabel(event.target.value)} />
      </Field>
    </EditDialog>
  );
}

export function SettingsKeys(): ReactNode {
  const credentials = useCredentials();
  const vendors = useDoor(useCallback(() => readHeldVendors(credentials), [credentials]));
  const catalogue = useDoor(useCallback(() => readCatalogue(credentials), [credentials]));
  const account = useDoor(useCallback(() => readNumbersAccount(credentials), [credentials]));
  const acting = useMove();
  // "" is a new key, a vendor's name its replacement.
  const [keying, setKeying] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const close = useCallback(() => (setKeying(null), setConnecting(false)), []);
  const held = [...(vendors.value ?? [])].sort((one, other) => brandOf(one).localeCompare(brandOf(other)));
  const removeKey = (vendor: string): void => void acting.move(async () => (await dropBoxKey(credentials, vendor), await vendors.reread())).catch(() => undefined);
  const removeAccount = (): void => void acting.move(async () => (await dropNumbersAccount(credentials), await account.reread())).catch(() => undefined);

  return (
    <>
      <Refusal>{vendors.refused ?? account.refused ?? acting.refused}</Refusal>
      <Section
        icon="brain"
        title="Provider keys"
        about="The vendors this deployment holds a key for. An organization with no key of its own runs on these, where it is lent them. A key is never shown again."
        action={
          <button type="button" className="cfg-save tst-action" onClick={() => setKeying("")}>
            <Icon name="plus" size={12} />
            Add a key
          </button>
        }
      >
        {vendors.value === undefined && vendors.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {vendors.value !== undefined && held.length === 0 && <p className="dash-quiet tst-none">No key yet. Every organization runs only on the keys it brings itself.</p>}
        {held.map((name) => (
          <div key={name} className="tst-row bxs-row">
            <Mark letter={brandOf(name).charAt(0)} />
            <span className="tst-row-words">
              <span className="tst-row-name">{brandOf(name)}</span>
              <span className="tst-row-under dash-clip">{doesSaid(catalogue.value, name)}</span>
            </span>
            <span className="tst-status bxs-status tst-status-held">Key held</span>
            <span className="bxs-acts">
              <button type="button" className="app-button" onClick={() => setKeying(name)}>
                Replace
              </button>
              <ConfirmButton label="Remove" asks="Calls on it will be refused. Remove?" danger onConfirm={() => removeKey(name)} />
            </span>
          </div>
        ))}
        {held.length > 0 && <p className="dash-quiet tst-none">Removing a key stops lending that vendor: an organization running on it is refused from its next call, unless it has its own key.</p>}
      </Section>

      <Section
        icon="numbers"
        title="Phone numbers account"
        about="The Twilio account every organization's numbers are bought on. Without one, nobody can buy a number here."
        action={
          account.value !== undefined && (
            <button type="button" className="cfg-save tst-action" onClick={() => setConnecting(true)}>
              {account.value === null ? "Connect Twilio" : "Replace"}
            </button>
          )
        }
      >
        {account.value === undefined && account.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {account.value === null && <p className="dash-quiet tst-none">Not connected. Organizations can still bring numbers from a carrier of their own.</p>}
        {account.value != null && (
          <div className="tst-row bxs-row">
            <span className="tst-row-words">
              <span className="tst-row-name">{account.value.label == null || account.value.label === "" ? "Twilio" : account.value.label}</span>
              <span className="tst-row-under bxs-code dash-clip">{account.value.account_sid}</span>
            </span>
            <span className="tst-status bxs-status tst-status-held">Connected</span>
            <ConfirmButton label="Remove" asks="Stop selling numbers?" danger onConfirm={removeAccount} />
          </div>
        )}
        {account.value != null && <p className="dash-quiet tst-none">Removing it stops new purchases. Numbers already bought keep ringing.</p>}
      </Section>

      {keying !== null && <KeyPanel key={keying} vendor={keying === "" ? null : keying} held={held} catalogue={catalogue.value} onKept={vendors.reread} onClose={close} />}
      {connecting && <NumbersPanel replaces={account.value != null} onKept={account.reread} onClose={close} />}
    </>
  );
}
