/** Organization list and the form that creates one. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Empty, Field, Input, Page, PageHead, Refused, TableHead, TableRow, TextAction } from "../../ui";
import { addOrg, readOrgs } from "./door";
import { useDoor, useMove } from "./use-door";
import "./box.css";

const COLUMNS = "minmax(0,1.2fr) minmax(0,1fr) minmax(0,1fr) 60px";

export function BoxOrgs(): ReactNode {
  const credentials = useCredentials();
  const orgs = useDoor(useCallback(() => readOrgs(credentials), [credentials]));
  const making = useMove();
  const [adding, setAdding] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");

  const make = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const made = await making.move(async () => {
      await addOrg(credentials, slug.trim(), name.trim());
      await orgs.reread();
    });
    if (made) {
      setSlug("");
      setName("");
      setAdding(false);
    }
  };

  return (
    <Page width={1060} tight>
      <PageHead title="Organizations" lede="Every tenant this box serves. Open one to see its people, its keys, its limits and the vendors it brought." />

      <Refused>{orgs.refused ?? making.refused}</Refused>

      {orgs.value !== undefined && (
        <Card>
          <CardHead
            title="On this box"
            meta={`${orgs.value.length} ${orgs.value.length === 1 ? "organization" : "organizations"}`}
            action={
              adding ? undefined : (
                <Button kind="primary" size="sm" className="ui-card-action" onClick={() => setAdding(true)}>
                  Add an organization
                </Button>
              )
            }
          />
          {adding && (
            <div className="box-inline">
              <form className="ui-form" onSubmit={(event) => void make(event)}>
                <Field label="Slug" grow minWidth={180}>
                  <Input value={slug} placeholder="tienda-sur" onChange={(event) => setSlug(event.target.value)} required autoFocus />
                </Field>
                <Field label="Name" grow minWidth={180}>
                  <Input value={name} placeholder="Tienda Sur (optional)" onChange={(event) => setName(event.target.value)} />
                </Field>
                <Button kind="primary" size="form" type="submit" disabled={making.busy || slug.trim() === ""}>
                  {making.busy ? "Adding…" : "Add"}
                </Button>
              </form>
              <div className="box-inline-foot">
                The slug is what people type and the gateway is its judge. Its first admin is invited from the org's Members tab.
                <span className="box-inline-close">
                  <TextAction onClick={() => setAdding(false)}>Close</TextAction>
                </span>
              </div>
            </div>
          )}
          {orgs.value.length === 0 ? (
            <Empty>No organization on this box yet. The first one is what a key is issued against.</Empty>
          ) : (
            <>
              <TableHead columns={COLUMNS} labels={["Organization", "Slug", "Id", ""]} />
              {orgs.value.map((org) => (
                <TableRow key={org.id} columns={COLUMNS} to={`/box/orgs/${encodeURIComponent(org.slug)}`}>
                  <span className="ui-cell-strong">{org.name}</span>
                  <span className="ui-cell-ink">{org.slug}</span>
                  <span className="ui-cell-faint box-fixed">{org.id}</span>
                  <span className="ui-cell-link ui-cell-end">Open</span>
                </TableRow>
              ))}
            </>
          )}
        </Card>
      )}
    </Page>
  );
}
