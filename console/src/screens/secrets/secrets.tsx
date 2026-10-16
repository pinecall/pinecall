/** Secrets: what the org's hosted apps are started with in this world — set, replaced and dropped, never shown. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { useWorld } from "../../lib/world";
import { Button, Card, Empty, Field, Input, Page, PageHead, Refused, TableHead, TextAction } from "../../ui";
import { dropSecret, putSecret, readSecrets, type Secret } from "./door";
import { nameRefused } from "./name";
import "./secrets.css";

const COLUMNS = "minmax(0,1.2fr) minmax(0,1fr) 150px 80px";

/**
 * A value typed here is sent once, on this request, and cleared from the form when it is kept: no
 * door answers one back, so a value that was lost is set again. Every door takes a key that opens
 * `app`; anyone else is shown the gateway's refusal.
 */
export function Secrets(): ReactNode {
  const credentials = useCredentials();
  const { world } = useWorld();
  const [secrets, setSecrets] = useState<Secret[] | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readSecrets(credentials).then(
      (kept) => {
        if (!gone) setSecrets(kept);
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
    const named = name.trim();
    const wrong = nameRefused(named) ?? (value === "" ? "A secret needs a value." : null);
    if (wrong !== null) {
      setRefused(wrong);
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      setSecrets(await putSecret(credentials, named, value));
      setValue("");
      setName("");
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const forget = async (named: string): Promise<void> => {
    if (!window.confirm(`Delete ${named}? Every hosted app of the org in ${world} restarts without it.`)) return;
    setRefused(null);
    try {
      setSecrets(await dropSecret(credentials, named));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Page tight>
      <PageHead
        title="Secrets"
        ledeWidth={660}
        lede={`What the org's hosted apps are started with in ${world}, as environment variables. A value is set or replaced here and never read back — not by this page, not by the CLI.`}
      />

      <Card pad>
        <form className="ui-form" onSubmit={(event) => void save(event)}>
          <Field label="Name" minWidth={200}>
            <Input value={name} placeholder="CRM_TOKEN" autoComplete="off" spellCheck={false} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Value, sent once" grow minWidth={220}>
            <Input type="password" value={value} autoComplete="new-password" onChange={(event) => setValue(event.target.value)} />
          </Field>
          <Button kind="primary" size="form" type="submit" disabled={busy || name.trim() === "" || value === ""}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </form>
        <div className="secrets-note">
          Setting or removing one restarts every hosted app of the org in {world}; the old process answers until the new one registers. A name
          starting with <span className="ui-fixed">PINECALL_</span> is the box's own.
        </div>
      </Card>

      <Refused>{refused}</Refused>

      <Card>
        {secrets !== null && secrets.length === 0 ? (
          <Empty>No secret in {world} yet. One set above, or with `pinecall secrets set`, is in every hosted app's environment from its next start.</Empty>
        ) : (
          <>
            <TableHead columns={COLUMNS} labels={["Name", "Set by", "Set", ""]} />
            {(secrets ?? []).map((one) => (
              <div key={one.name} className="ui-table-row" style={{ gridTemplateColumns: COLUMNS }}>
                <span className="ui-cell-strong ui-clip ui-fixed">{one.name}</span>
                <span className="ui-cell-ink ui-clip">{one.set_by}</span>
                <span className="ui-cell-faint">{dayAndTime(one.set_at)}</span>
                <span className="ui-cell-end">
                  <TextAction danger onClick={() => void forget(one.name)}>
                    Delete
                  </TextAction>
                </span>
              </div>
            ))}
          </>
        )}
      </Card>
    </Page>
  );
}
