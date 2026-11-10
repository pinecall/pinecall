/** The vendors the org's calls run on: which run on its own key, which Pinecall lends, which need a key brought, and the way to bring one or take it back. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { brandOf } from "../configure/vendors";
import { Icon } from "../shell/icons";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { dropVendorKey, keepVendorKey, readVendors, type Vendor } from "./door";

const STAGES: Record<string, string> = { stt: "Transcriber", llm: "Model", tts: "Voice", realtime: "Realtime" };
const STANDING: Record<string, { mood: "held" | "none" | "waiting" | "broke"; said: string }> = {
  yours: { mood: "held", said: "Your key" },
  offered: { mood: "none", said: "Lent by Pinecall" },
  "bring your own": { mood: "waiting", said: "Needs your key" },
  broken: { mood: "broke", said: "Its key fails" },
};

function KeyPanel({ vendor, onKept, onClose }: { vendor: Vendor; onKept: () => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const brand = brandOf(vendor.name);
  const keep = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    keepVendorKey(credentials, vendor.name, key.trim()).then(() => (onKept(), onClose()), (failed: unknown) => setRefused(saidBy(failed))).finally(() => setBusy(false));
  };
  return (
    <SidePanel
      title={`Your ${brand} key`}
      icon="settings"
      about={`Your calls run on it from the next one, any ${brand} model, billed by ${brand} to you. It is kept encrypted and never shown again.`}
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            <button type="button" className="app-button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form="vendor-key" className="cfg-save" disabled={busy || key.trim() === ""}>
              {busy ? "Saving…" : "Save key"}
            </button>
          </div>
        </>
      }
    >
      <form id="vendor-key" className="cfg-dialog-body" onSubmit={keep}>
        <Field label="API key">
          <input className="cfg-input" type="password" aria-label="API key" placeholder={`Paste your ${brand} API key`} autoFocus autoComplete="new-password" value={key} onChange={(event) => setKey(event.target.value)} />
        </Field>
      </form>
    </SidePanel>
  );
}

export function Providers(): ReactNode {
  const credentials = useCredentials();
  const [vendors, setVendors] = useState<Vendor[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const reread = useCallback((): void => void readVendors(credentials).then(setVendors, (failed: unknown) => (setVendors([]), setRefused(saidBy(failed)))), [credentials]);
  useEffect(reread, [reread]);

  // The org's own first, then what it must bring, then what is lent: the ones it can act on lead.
  const rank = (one: Vendor): number => ({ broken: 0, yours: 1, "bring your own": 2, offered: 3 })[one.availability ?? "offered"] ?? 3;
  const ordered = [...(vendors ?? [])].sort((one, other) => rank(one) - rank(other) || brandOf(one.name).localeCompare(brandOf(other.name)));
  const picked = ordered.find((one) => one.name === open);

  return (
    <>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      <section className="tst-list set-tone-pink" aria-label="Providers">
        <header className="tst-head">
          <span className="tst-head-mark" aria-hidden="true">
            <Icon name="brain" size={16} />
          </span>
          <span className="tst-head-words">
            <span className="tst-head-title">Providers</span>
            <span className="tst-head-about">The vendors your calls run on. With your own key, any of its models; without one, what Pinecall lends you.</span>
          </span>
        </header>
        {vendors === null && <p className="dash-quiet tst-none">Reading…</p>}
        {ordered.map((one) => {
          const standing = STANDING[one.availability ?? "offered"] ?? { mood: "none" as const, said: one.availability ?? "" };
          const own = one.availability === "yours" || one.availability === "broken";
          return (
            <div key={one.name} className="tst-row set-row">
              <span className="tst-mark" aria-hidden="true">
                {brandOf(one.name).charAt(0)}
              </span>
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <span className="dash-clip">{brandOf(one.name)}</span>
                </span>
                <span className="tst-row-under dash-clip">{one.does.map((stage) => STAGES[stage] ?? stage).join(", ")}</span>
              </span>
              <span className={`tst-status set-status tst-status-${standing.mood}`}>{standing.said}</span>
              <span className="set-acts">
                <button type="button" className="app-button" onClick={() => setOpen(one.name)}>
                  {own ? "Replace key" : "Add key"}
                </button>
                {own && <ConfirmButton label="Remove" asks="Remove your key?" danger onConfirm={() => void dropVendorKey(credentials, one.name).then(reread, (failed: unknown) => setRefused(saidBy(failed)))} />}
              </span>
            </div>
          );
        })}
      </section>
      {picked !== undefined && <KeyPanel key={picked.name} vendor={picked} onKept={reread} onClose={close} />}
    </>
  );
}
