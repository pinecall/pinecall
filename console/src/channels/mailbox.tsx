/** A mailbox an agent answers: where it is read, where its replies leave, the name its contacts read; its server changed in place. */

import { useState, type ReactNode } from "react";

import type { Carrier } from "../numbers/door";
import { MailboxForm } from "../numbers/email-way";
import { useMove } from "../numbers/parts";

const portSaid = (carrier: Carrier, host: string, port: string): string => `${String(carrier.settings[host] ?? "—")}:${String(carrier.settings[port] ?? "")}`;

export function MailboxCard({ carrier, onSaved }: { carrier: Carrier; onSaved: () => Promise<void> }): ReactNode {
  const [editing, setEditing] = useState(false);
  const mover = useMove();
  const relay = String(carrier.settings["smtp_username"] ?? "") !== "";
  const name = String(carrier.settings["sender_name"] ?? "");
  return (
    <div className="mail-box">
      <div className="mail-box-head">
        <span className="mail-box-who">
          <span className="mail-name">{name === "" ? carrier.account : `${name} <${carrier.account}>`}</span>
          <span className="mail-address">
            Reads {portSaid(carrier, "imap_host", "imap_port")} · answers through {portSaid(carrier, "smtp_host", "smtp_port")}
            {relay ? ", a relay with its own login" : ""}
          </span>
        </span>
        <button type="button" className={editing ? "app-button calls-toggle calls-toggle-on" : "app-button"} aria-expanded={editing} onClick={() => setEditing(!editing)}>
          {editing ? "Close" : "Server settings"}
        </button>
      </div>
      {editing && (
        <>
          {mover.refused !== null && (
            <p className="cfg-refused" role="alert">
              {mover.refused}
            </p>
          )}
          <MailboxForm
            editing={carrier}
            mover={mover}
            onSaved={async () => {
              await onSaved();
              setEditing(false);
            }}
          />
        </>
      )}
    </div>
  );
}
