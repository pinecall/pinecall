/** Brand settings for the box's emails (name, logo, accent) with a header preview. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, Refused } from "../../ui";
import { readBrand, saveBrand } from "./door-settings";
import { NoSuchDoor } from "./settings";
import { useDoor, useMove } from "./use-door";

const NAME = "Pinecall";
const ACCENT = "#5b3df5";
const A_COLOUR = /^#[0-9a-fA-F]{6}$/;

export function SettingsBrand(): ReactNode {
  const credentials = useCredentials();
  const brand = useDoor(useCallback(() => readBrand(credentials), [credentials]));
  const acting = useMove();
  const [name, setName] = useState(NAME);
  const [logo, setLogo] = useState("");
  const [accent, setAccent] = useState(ACCENT);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (brand.value === undefined || brand.value === null) return;
    setName(brand.value.name ?? NAME);
    setLogo(brand.value.logo_url ?? "");
    setAccent(brand.value.accent ?? ACCENT);
  }, [brand.value]);

  if (brand.value === undefined) return <Refused>{brand.refused}</Refused>;
  if (brand.value === null) return <NoSuchDoor />;

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setSaved(false);
    setSaved(
      await acting.move(async () => {
        await saveBrand(credentials, { name: name.trim(), logo_url: logo.trim(), accent });
        await brand.reread();
      }),
    );
  };

  // Free-typed: only preview it once it parses as a colour.
  const painted = A_COLOUR.test(accent) ? accent : ACCENT;

  return (
    <>
      <Refused>{acting.refused}</Refused>
      <Card>
        <CardHead title="What the letters carry" meta="invitations and password resets, for every org on this box" />
        <form className="box-form" onSubmit={(event) => void save(event)}>
          <div className="box-form-grid">
            <Field label="Name">
              <Input value={name} onChange={(event) => setName(event.target.value)} required />
            </Field>
            <Field label="Accent">
              <span className="box-accent">
                <input type="color" className="box-accent-well" value={painted} onChange={(event) => setAccent(event.target.value)} aria-label="Accent" />
                <Input value={accent} onChange={(event) => setAccent(event.target.value)} />
              </span>
            </Field>
            <Field label="Logo URL">
              <Input type="url" value={logo} placeholder="https://… (https only; empty shows the name)" onChange={(event) => setLogo(event.target.value)} />
            </Field>
          </div>
          <div className="box-line">
            <Button kind="primary" size="md" type="submit" disabled={acting.busy}>
              {acting.busy ? "Saving…" : "Save"}
            </Button>
            {saved && <span className="box-done">Saved. The next letter carries it.</span>}
          </div>
        </form>
      </Card>

      <Card>
        <CardHead title="Preview" meta="the head of a letter" />
        <div className="box-letter-ground">
          <div className="box-letter">
            {logo.trim().startsWith("https://") ? <img className="box-letter-logo" src={logo.trim()} alt={name} /> : <span className="box-letter-name">{name}</span>}
            <div className="box-letter-title">You're invited to Acme on {name}</div>
            <div className="box-letter-words">Ana invited you as a supervisor. Choose a password to take your first key.</div>
            <span className="box-letter-button" style={{ background: painted }}>
              Accept the invitation
            </span>
          </div>
        </div>
      </Card>
    </>
  );
}
