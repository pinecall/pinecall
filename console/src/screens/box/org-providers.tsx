/** Vendor keys an org brings itself: set one, or revert to the box's. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Empty, Field, Input, Refused, Row, TextAction } from "../../ui";
import { bringVendor, forgetVendor, readVendors } from "./door";
import { useDoor, useMove } from "./use-door";

export function OrgProviders({ named }: { named: string }): ReactNode {
  const credentials = useCredentials();
  const vendors = useDoor(useCallback(() => readVendors(credentials, named), [credentials, named]));
  const acting = useMove();
  const [bringing, setBringing] = useState(false);
  const [vendor, setVendor] = useState("");
  const [key, setKey] = useState("");

  const bring = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const kept = await acting.move(async () => {
      await bringVendor(credentials, named, vendor.trim(), key.trim());
      await vendors.reread();
    });
    if (kept) {
      setVendor("");
      setKey("");
      setBringing(false);
    }
  };

  return (
    <>
      <Refused>{vendors.refused ?? acting.refused}</Refused>
      {vendors.value !== undefined && (
        <Card>
          <CardHead
            title="Vendors it brought"
            meta="every other vendor runs on the box's own key"
            action={
              bringing ? undefined : (
                <Button kind="primary" size="sm" className="ui-card-action" onClick={() => setBringing(true)}>
                  Bring a key
                </Button>
              )
            }
          />
          {bringing && (
            <div className="box-inline">
              <form className="ui-form" onSubmit={(event) => void bring(event)}>
                <Field label="Vendor" minWidth={170}>
                  <Input value={vendor} placeholder="elevenlabs" onChange={(event) => setVendor(event.target.value)} required autoFocus />
                </Field>
                <Field label="Its key, sent once" grow minWidth={240}>
                  <Input type="password" autoComplete="off" value={key} placeholder="never shown again" onChange={(event) => setKey(event.target.value)} required />
                </Field>
                <Button kind="primary" size="form" type="submit" disabled={acting.busy}>
                  {acting.busy ? "Keeping…" : "Keep it"}
                </Button>
              </form>
              <div className="box-inline-foot">
                No door a person reads ever answers with a provider key: a lost one is set again.
                <span className="box-inline-close">
                  <TextAction onClick={() => setBringing(false)}>Close</TextAction>
                </span>
              </div>
            </div>
          )}
          {vendors.value.length === 0 ? (
            <Empty>None: every call of this org runs on the keys of the box.</Empty>
          ) : (
            vendors.value.map((one) => (
              <Row
                key={one}
                name={one}
                sub="this org's own account with them"
                end={
                  <TextAction
                    disabled={acting.busy}
                    onClick={() =>
                      void acting.move(async () => {
                        await forgetVendor(credentials, named, one);
                        await vendors.reread();
                      })
                    }
                  >
                    Give it back to the box
                  </TextAction>
                }
              />
            ))
          )}
        </Card>
      )}
    </>
  );
}
