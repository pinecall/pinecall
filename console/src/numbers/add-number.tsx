/** Add a number, in the side panel: the ways this deployment offers, then the form of the one picked, then what a call to the new number goes through. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Icon } from "../shell/icons";
import { SidePanel } from "../ui/side-panel";
import { readCarriers, readCatalog, readOwned, type Carrier, type Catalog, type Owned } from "./door";
import { Path, useMove } from "./parts";
import { BuyWay, GuidedWay, PbxWay, TwilioWay, WhatsAppWay, type WayProps } from "./ways";
import { shown, waysOffered, type Way } from "./words";

function Form({ way, ...props }: WayProps & { way: Way }): ReactNode {
  switch (way.id) {
    case "buy":
      return <BuyWay {...props} />;
    case "twilio":
      return <TwilioWay {...props} />;
    case "guided":
      return <GuidedWay way={way} {...props} />;
    case "pbx":
      return <PbxWay {...props} />;
    case "whatsapp":
      return <WhatsAppWay {...props} />;
  }
}

/** `agent` opens it for one agent, which every way then rings; `channel` keeps it to the phone's ways or to WhatsApp. */
export function AddNumberPanel({ agents, agent, channel = null, onAdded, onClose }: { agents: readonly string[]; agent?: string | undefined; channel?: "phone" | "whatsapp" | null; onAdded: (number: string) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const mover = useMove();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  const [owned, setOwned] = useState<Owned[]>([]);
  const [refused, setRefused] = useState<string | null>(null);
  const [way, setWay] = useState<Way | null>(null);
  const [added, setAdded] = useState<{ number: string; after: ReactNode } | null>(null);

  const readAccounts = useCallback(async (): Promise<void> => {
    const [accounts, theirs] = await Promise.all([readCarriers(credentials), readOwned(credentials)]);
    setCarriers(accounts);
    setOwned(theirs);
  }, [credentials]);

  useEffect(() => {
    readCatalog(credentials).then(setCatalog, (failed: unknown) => setRefused(saidBy(failed)));
    readAccounts().catch((failed: unknown) => setRefused(saidBy(failed)));
  }, [credentials, readAccounts]);

  const ways = catalog === null ? [] : waysOffered(catalog, channel);
  // One way alone is no choice: its form is the panel.
  const only = ways.length === 1 ? ways[0] : undefined;
  const open = way ?? only ?? null;
  const title = added !== null ? shown(added.number) : open !== null ? open.name : channel === "whatsapp" ? "Connect WhatsApp" : "Add a number";

  return (
    <SidePanel
      title={title}
      icon={channel === "whatsapp" ? "chat" : "numbers"}
      about={added !== null ? undefined : open === null ? (agent === undefined ? "Every way ends the same: a number that reaches one of your agents." : `Every way ends the same: a number that reaches ${agent}.`) : open.says}
      onClose={onClose}
      footer={
        added !== null ? (
          <div className="cfg-dialog-foot">
            <button type="button" className="cfg-save" onClick={onClose}>
              Done
            </button>
          </div>
        ) : undefined
      }
    >
      {(refused ?? mover.refused) !== null && (
        <p className="cfg-refused" role="alert">
          {refused ?? mover.refused}
        </p>
      )}
      {added !== null ? (
        <>
          <p className="num-added">
            <Icon name="check" size={15} />
            {shown(added.number)} is yours here.
          </p>
          {added.after}
          <Path number={added.number} />
        </>
      ) : open === null ? (
        <div className="num-ways">
          {catalog === null && refused === null && <p className="dash-quiet">Reading the ways…</p>}
          {ways.map((one) => (
            <button key={`${one.id}:${one.via ?? ""}`} type="button" className="num-way" onClick={() => setWay(one)}>
              <span className="num-way-mark">
                <Icon name={one.icon} size={17} />
              </span>
              <span className="num-way-words">
                <span className="num-way-name">{one.name}</span>
                <span className="num-way-says">{one.says}</span>
              </span>
              <Icon name="chevron" size={15} />
            </button>
          ))}
        </div>
      ) : (
        <>
          {only === undefined && (
            <button type="button" className="num-link num-back" onClick={() => setWay(null)}>
              Another way
            </button>
          )}
          <Form
            way={open}
            agents={agents}
            agent={agent}
            carriers={carriers}
            owned={owned}
            mover={mover}
            sipDomain={catalog?.sip_domain ?? null}
            onAccount={readAccounts}
            onAdded={(number, after) => {
              setAdded({ number, after: after ?? null });
              onAdded(number);
            }}
          />
        </>
      )}
    </SidePanel>
  );
}
