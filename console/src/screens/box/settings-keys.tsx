/** The box's own keys: the vendor keys it lends its orgs, and the Twilio account it buys their numbers on. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readCatalogue, type Catalogue } from "../../lib/catalogue";
import { Button, Card, CardHead, Field, Input, KV, Pill, Refused, Select, SelectItem, TextAction } from "../../ui";
import { dropBoxKey, dropNumbersAccount, readBoxVendors, readNumbersAccount, saveNumbersAccount, setBoxKey } from "./door-box";
import { useDoor, useMove } from "./use-door";

/** Both halves of "whose key": the box's, here; each org's own, on its page under Vendors it brought. */
export function SettingsKeys(): ReactNode {
  return (
    <>
      <VendorKeys />
      <TheNumbersAccount />
    </>
  );
}

/** Every vendor the box holds a key for; a key typed here is sent once and never read back. */
function VendorKeys(): ReactNode {
  const credentials = useCredentials();
  const vendors = useDoor(useCallback(() => readBoxVendors(credentials), [credentials]));
  const acting = useMove();
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [vendor, setVendor] = useState("");
  const [key, setKey] = useState("");

  useEffect(() => {
    let gone = false;
    readCatalogue(credentials).then((read) => {
      if (!gone) setCatalogue(read);
    }, () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials]);
  const kept = vendors.value ?? [];
  const names = [...new Set([...(catalogue?.providers.map((one) => one.name) ?? []), ...kept])].sort();

  const hold = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const done = await acting.move(async () => {
      await setBoxKey(credentials, vendor.trim(), key);
      await vendors.reread();
    });
    if (done) {
      setVendor("");
      setKey("");
    }
  };

  return (
    <Card>
      <CardHead title="Vendor API keys" meta="Pinecall pays the model, voice and speech vendors with these when an org has no key of its own" />
      <div className="box-kvs">
        {kept.length === 0 && <span className="ui-note">No key saved yet: every org runs only on the keys it adds itself.</span>}
        {kept.map((name) => (
          <KV key={name} label={name} keyWidth={140}>
            <span className="box-key-row">
              <Pill tone="green">key saved</Pill>
              <TextAction danger onClick={() => void acting.move(async () => { await dropBoxKey(credentials, name); await vendors.reread(); })}>
                Remove
              </TextAction>
            </span>
          </KV>
        ))}
      </div>
      <form className="box-form" onSubmit={(event) => void hold(event)}>
        <div className="box-form-grid">
          <Field label="Vendor">
            <Select value={vendor} onValueChange={setVendor} placeholder="Choose a vendor…" required>
              {names.map((name) => (
                <SelectItem key={name} value={name}>
                  {kept.includes(name) ? `${name} · replaces the saved key` : name}
                </SelectItem>
              ))}
            </Select>
          </Field>
          <Field label="API key">
            <Input type="password" autoComplete="new-password" value={key} placeholder="paste it here" onChange={(event) => setKey(event.target.value)} required />
          </Field>
        </div>
        <div className="box-line">
          <Button kind="primary" size="md" type="submit" disabled={acting.busy}>
            {acting.busy ? "Saving…" : "Save key"}
          </Button>
          <span className="ui-note">Stored encrypted and never shown again. Which orgs may use it: Limits of each org, and the Admission tab for new ones.</span>
        </div>
      </form>
      <Refused>{vendors.refused ?? acting.refused}</Refused>
    </Card>
  );
}

/** The Twilio account the box buys every org's numbers on; without one it sells none. */
function TheNumbersAccount(): ReactNode {
  const credentials = useCredentials();
  const account = useDoor(useCallback(() => readNumbersAccount(credentials), [credentials]));
  const acting = useMove();
  const [editing, setEditing] = useState(false);
  const [sid, setSid] = useState("");
  const [user, setUser] = useState("");
  const [secret, setSecret] = useState("");
  const [label, setLabel] = useState("");

  if (account.value === undefined) return <Refused>{account.refused}</Refused>;
  const held = account.value;
  const form = editing || held === null;

  const keep = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const kept = await acting.move(async () => {
      await saveNumbersAccount(credentials, { account_sid: sid.trim(), user: user.trim() || sid.trim(), secret, label: label.trim() });
      await account.reread();
    });
    if (kept) {
      setSecret("");
      setEditing(false);
    }
  };

  return (
    <Card>
      <CardHead title="Twilio account for buying numbers" meta="When any org buys a phone number in Pinecall, it is bought on this account">
        <span className="box-head-moves">
          <Pill tone={held === null ? "gray" : "green"}>{held === null ? "not connected" : "connected"}</Pill>
        </span>
      </CardHead>
      {form ? (
        <form className="box-form" onSubmit={(event) => void keep(event)}>
          <div className="box-form-grid">
            <Field label="Account SID">
              <Input value={sid} placeholder="AC…" onChange={(event) => setSid(event.target.value)} required autoComplete="off" />
            </Field>
            <Field label="API key SID (starts with SK; empty to use the account SID)">
              <Input value={user} placeholder="SK…" onChange={(event) => setUser(event.target.value)} autoComplete="off" />
            </Field>
            <Field label="Secret, sent once">
              <Input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} required autoComplete="new-password" />
            </Field>
            <Field label="Name (optional)">
              <Input value={label} placeholder="Pinecall" onChange={(event) => setLabel(event.target.value)} autoComplete="off" />
            </Field>
          </div>
          <div className="box-line">
            <Button kind="primary" size="md" type="submit" disabled={acting.busy}>
              {acting.busy ? "Checking with Twilio…" : "Keep this account"}
            </Button>
            {editing && <TextAction onClick={() => setEditing(false)}>Cancel</TextAction>}
            <span className="ui-note">Checked with Twilio before saving, stored encrypted, never shown again. Each number an org buys counts against its Numbers limit.</span>
          </div>
        </form>
      ) : (
        <div className="box-kvs">
          <KV label="Account" keyWidth={120}>
            <span className="box-fixed">{held.label === "" ? held.account_sid : `${held.label} · ${held.account_sid}`}</span>
          </KV>
          <div className="box-line box-kvs-moves">
            <TextAction onClick={() => setEditing(true)}>Replace</TextAction>
            <TextAction danger onClick={() => void acting.move(async () => { await dropNumbersAccount(credentials); await account.reread(); })}>
              Remove
            </TextAction>
          </div>
          <div className="box-limit-about">Removing it stops orgs from buying new numbers. Numbers already bought keep working.</div>
        </div>
      )}
      <Refused>{acting.refused}</Refused>
    </Card>
  );
}
