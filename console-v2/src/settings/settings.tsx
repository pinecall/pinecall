/** Settings: for now, the deployment's brand — the name, logo and colour its sign-in page and its emails carry — with the sign-in drawn as it will look. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { z } from "zod";

import { put, read, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../lib/org";
import { BrandMark, wornBy } from "../login/way-in";
import "./settings.css";

const DOOR = "/v1/ops/brand";
const BrandSchema = z.object({ name: z.string(), logo_url: z.string().nullable(), accent: z.string() });
const A_COLOUR = /^#[0-9a-fA-F]{6}$/;

export function Settings(): ReactNode {
  const { whose } = useOrg();
  if (whose === null) return null;
  if (whose.operator !== true) {
    return (
      <p className="set-lede">The name and logo on the sign-in page belong to whoever runs this deployment. Ask them to change it.</p>
    );
  }
  return <Branding />;
}

function Branding(): ReactNode {
  const credentials = useCredentials();
  const [name, setName] = useState("");
  const [logo, setLogo] = useState("");
  const [accent, setAccent] = useState("#5b3df5");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    read(credentials, DOOR).then(
      (said) => {
        if (gone) return;
        const brand = BrandSchema.parse(said);
        setName(brand.name);
        setLogo(brand.logo_url ?? "");
        setAccent(brand.accent);
        setLoaded(true);
      },
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setRefused(null);
    try {
      await put(credentials, DOOR, { name: name.trim(), logo_url: logo.trim(), accent: accent.trim() });
      setSaved(true);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setSaving(false);
    }
  };

  const shownAccent = A_COLOUR.test(accent) ? accent : "#5b3df5";
  const shown = { name: name.trim() === "" ? "Pinecall" : name.trim(), logo_url: logo.trim() === "" ? null : logo.trim(), accent: shownAccent };
  return (
    <>
      <h2 className="set-title">Branding</h2>
      <p className="set-lede">What your sign-in page and emails carry, for everyone on this deployment.</p>
      <div className="set-pair">
        <form className="set-form" onSubmit={(event) => void save(event)}>
          <label className="set-field">
            Name
            <input className="set-input" value={name} maxLength={80} disabled={!loaded} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="set-field">
            Logo URL
            <input className="set-input" type="url" value={logo} placeholder="https://example.com/logo.svg" disabled={!loaded} onChange={(event) => setLogo(event.target.value)} />
            <span className="set-help">An https:// image, about 30 px tall when drawn. Leave it empty to show your name.</span>
          </label>
          <label className="set-field">
            Colour
            <span className="set-colour">
              <input type="color" className="set-swatch" value={shownAccent} disabled={!loaded} aria-label="Pick the colour" onChange={(event) => setAccent(event.target.value)} />
              <input className="set-input" value={accent} disabled={!loaded} onChange={(event) => setAccent(event.target.value)} />
            </span>
          </label>
          <div className="set-foot">
            <button type="submit" className="set-save" disabled={!loaded || saving}>
              {saving ? "Saving…" : "Save branding"}
            </button>
            {saved && <span className="set-saved">Saved</span>}
          </div>
          {refused !== null && (
            <p className="set-refused" role="alert">
              {refused}
            </p>
          )}
        </form>
        <div className="set-preview login" style={wornBy(shown)} aria-label="How the sign-in page will look">
          <div className="login-brand">
            <BrandMark brand={shown} />
          </div>
          <p className="set-preview-title">Sign in</p>
          <span className="set-preview-field" />
          <span className="set-preview-field" />
          <span className="set-preview-go">Sign in</span>
        </div>
      </div>
    </>
  );
}
