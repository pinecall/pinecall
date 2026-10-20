/** Providers: every vendor this build runs, what each one still wants, and the keys this org brought. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import type { Catalogue } from "../../lib/catalogue";
import { useLimits } from "../../lib/limits";
import { Button, Card, Field, Input, Page, PageHead, Refused, Select, SelectItem } from "../../ui";
import { addKey, readCatalogue, readVendors, removeKey } from "./door";
import { OtherVendors, RunningOn, FOR } from "./vendor-lists";
import "./providers.css";

/**
 * The screen. A key typed here is sent once, on this request — exactly the path `pinecall providers
 * add` takes, which reads it off stdin for the same reason a flag is refused there: argv is visible
 * to every user on the box. No door a person reads answers with a provider key — the one that does
 * is the worker's, an org's own keys to its own process — so this page lists vendors and nothing
 * more. A key that was lost is set again.
 */
export function Providers(): ReactNode {
  const credentials = useCredentials();
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [brought, setBrought] = useState<string[] | null>(null);
  const [vendor, setVendor] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // What the box lends this org: null until read, and then every vendor when `lends` is null.
  const limits = useLimits();

  const reread = async (): Promise<void> => setBrought(await readVendors(credentials));

  useEffect(() => {
    let gone = false;
    const failed = (why: unknown): void => {
      if (!gone) setRefused(why instanceof Error ? why.message : String(why));
    };
    readCatalogue(credentials).then((whole) => {
      if (!gone) setCatalogue(whole);
    }, failed);
    readVendors(credentials).then((theirs) => {
      if (!gone) setBrought(theirs);
    }, failed);
    return () => {
      gone = true;
    };
  }, [credentials]);

  const add = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      await addKey(credentials, vendor.trim(), key);
      // Out of the page the moment it is out of this process: nothing here keeps it to show later.
      setKey("");
      setVendor("");
      await reread();
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  const give = async (name: string): Promise<void> => {
    setRefused(null);
    try {
      await removeKey(credentials, name);
      await reread();
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };

  const providers = catalogue?.providers ?? [];
  const theirs = new Set(brought ?? []);
  const lends = limits === null ? null : limits.lends;

  return (
    <Page tight>
      <PageHead
        title="Providers"
        ledeWidth={660}
        lede="The companies behind your agents' language model, speech recognition and voice. A key you add is stored encrypted and never shown again."
      />

      <RunningOn providers={providers} brought={theirs} lends={lends} onGiveBack={(name) => void give(name)} />

      <Card pad>
        <form className="ui-form" onSubmit={(event) => void add(event)}>
          <Field label="Add your own key for" minWidth={220}>
            <Select value={vendor} onValueChange={(value) => setVendor(value)} placeholder="Choose a vendor…">
              {providers
                .filter((one) => one.env !== null)
                .map((one) => (
                  <SelectItem key={one.name} value={one.name}>
                    {one.name} · {one.does.map((kind) => FOR[kind]).join(", ")}
                  </SelectItem>
                ))}
            </Select>
          </Field>
          <Field label="API key" grow minWidth={220}>
            <Input type="password" value={key} placeholder="paste it here" autoComplete="new-password" onChange={(event) => setKey(event.target.value)} />
          </Field>
          <Button kind="primary" size="form" type="submit" disabled={busy || vendor.trim() === "" || key === ""}>
            {busy ? "Saving…" : "Save key"}
          </Button>
        </form>
        <div className="prov-hint">A key you add is used for every call of this org from the next one, and takes the place of the runtime's key for that vendor.</div>
      </Card>

      <Refused>{refused}</Refused>

      <OtherVendors providers={providers} brought={theirs} lends={lends} />
    </Page>
  );
}
