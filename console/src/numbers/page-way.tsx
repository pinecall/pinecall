/** Messenger & Instagram: a Facebook Page of the org's connected once (its id, a Page token, its Meta app's secret), then its Messenger and its Instagram given to an agent. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Field } from "../ui/setting";
import { addNumber, bringCarrier, readSubscription, type Carrier, type Subscription } from "./door";
import { AgentField, Copy, type Mover } from "./parts";
import { Submit, type WayProps } from "./ways";

/** What the org types in its Meta app so the Page's messages come here: Messenger's webhook, and Instagram's. */
export function PageWebhook(): ReactNode {
  const credentials = useCredentials();
  const [told, setTold] = useState<Subscription | null>(null);
  useEffect(() => {
    let asked = true;
    void readSubscription(credentials).then((subscription) => asked && setTold(subscription), () => undefined);
    return () => void (asked = false);
  }, [credentials]);
  if (told === null) return null;
  return (
    <>
      <p className="num-hint">
        In your Meta app, open Messenger ▸ Messenger API Settings ▸ Configure webhooks, and Instagram&apos;s webhooks too for its account: set both to these two values and subscribe to <code>messages</code>. The Page itself is subscribed to the app when it is connected here.
      </p>
      <dl className="num-setup">
        <dt>Callback URL</dt>
        <dd>
          <Copy text={told.callback_url} />
        </dd>
        <dt>Verify token</dt>
        <dd>
          <Copy text={told.verify_token} />
        </dd>
      </dl>
    </>
  );
}

/** The Page's fields: its id, a Page token, the app's secret (left empty when it is connected again, to keep it), a name. */
export function PageForm({ mover, onBring }: { mover: Mover; onBring: (page: string) => Promise<void> }): ReactNode {
  const credentials = useCredentials();
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [label, setLabel] = useState("");
  const bring = (event: FormEvent): void => {
    event.preventDefault();
    const page = pageId.trim();
    void mover
      .move(() =>
        bringCarrier(credentials, {
          kind: "messenger",
          page_id: page,
          access_token: token.trim(),
          ...(appSecret.trim() === "" ? {} : { app_secret: appSecret.trim() }),
          ...(label.trim() === "" ? {} : { label: label.trim() }),
        }),
      )
      .then(() => onBring(page), () => undefined);
  };
  return (
    <form className="num-form" onSubmit={bring}>
      <p className="num-hint">Connect the Page once. Its token is checked with Meta, kept encrypted, and never shown again; the Instagram account linked to the Page is found by Meta and answered too.</p>
      <Field label="Page ID">
        <input className="cfg-input" aria-label="Page ID" placeholder="From your Meta app's Messenger API settings" required inputMode="numeric" pattern="\d{5,32}" spellCheck={false} autoComplete="off" value={pageId} onChange={(event) => setPageId(event.target.value)} />
      </Field>
      <Field label="Page access token">
        <input className="cfg-input" type="password" aria-label="Page access token" placeholder="Generated for the Page in the same settings" required autoComplete="new-password" spellCheck={false} value={token} onChange={(event) => setToken(event.target.value)} />
      </Field>
      <Field label="App secret">
        <input className="cfg-input" type="password" aria-label="App secret" placeholder="Your Meta app's, from App settings ▸ Basic" autoComplete="new-password" spellCheck={false} value={appSecret} onChange={(event) => setAppSecret(event.target.value)} />
      </Field>
      <Field label="Name">
        <input className="cfg-input" aria-label="Name" placeholder="Optional: the Page's own name when left empty" autoComplete="off" value={label} onChange={(event) => setLabel(event.target.value)} />
      </Field>
      <PageWebhook />
      <Submit busy={mover.busy} doing="Connecting…" disabled={pageId.trim() === "" || token.trim() === ""}>
        Connect the Page
      </Submit>
    </form>
  );
}

/** The ids a Page answers at: its own on Messenger, its linked Instagram account's on Instagram. */
function routesOf(page: Carrier): { number: string; channel: "messenger" | "instagram" }[] {
  const instagram = page.settings["instagram_id"];
  return [{ number: page.account, channel: "messenger" }, ...(instagram === undefined ? [] : [{ number: String(instagram), channel: "instagram" as const }])];
}

/** Add ▸ Messenger & Instagram: the Page connected once, then its Messenger and its Instagram both reach the agent picked. */
export function PageWay({ agents, agent: fixed, carriers, mover, onAccount, onAdded }: WayProps): ReactNode {
  const credentials = useCredentials();
  const pages = carriers.filter((one) => one.kind === "messenger");
  const [picked, setPicked] = useState("");
  const [another, setAnother] = useState(false);
  const [agent, setAgent] = useState(fixed ?? agents[0] ?? "");
  const page = pages.find((one) => one.account === picked) ?? pages[0];

  const route = async (connected: Carrier): Promise<void> => {
    for (const one of routesOf(connected)) await mover.move(() => addNumber(credentials, { ...one, agent, account: connected.account }, false));
    const both = routesOf(connected).length === 2;
    onAdded(connected.account, <p className="num-hint">{both ? "Messages to the Page on Messenger and to its Instagram account reach the agent now." : "Messages to the Page on Messenger reach the agent now. Link an Instagram professional account to the Page, connect it again, and Instagram is answered too."}</p>);
  };

  if (page === undefined || another) {
    return (
      <PageForm
        mover={mover}
        onBring={async (id) => {
          await onAccount();
          setPicked(id);
          setAnother(false);
        }}
      />
    );
  }
  const connect = (event: FormEvent): void => {
    event.preventDefault();
    void route(page).catch(() => undefined);
  };
  return (
    <form className="num-form" onSubmit={connect}>
      <p className="num-hint">
        {page.label === "" ? `Page ${page.account}` : page.label}: {routesOf(page).length === 2 ? "its Messenger and its Instagram account" : "its Messenger (no Instagram account is linked to it yet)"}.
      </p>
      <button type="button" className="num-link" onClick={() => setAnother(true)}>
        Connect another Page
      </button>
      <AgentField agents={agents} fixed={fixed !== undefined} value={agent} onChange={setAgent} />
      <Submit busy={mover.busy} doing="Connecting…" disabled={agent === ""}>
        Answer them
      </Submit>
    </form>
  );
}
