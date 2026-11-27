/** An agent's Channels tab: its phone, WhatsApp and SMS numbers, its mailboxes and its Facebook Pages, each with how it is reached, the way to add another, and the email template. */

import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { ago } from "../lib/format";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { Icon, type IconName } from "../shell/icons";
import { AddNumberPanel } from "../numbers/add-number";
import type { NumberRow } from "../numbers/door";
import { useNumbers } from "../numbers/numbers";
import { TestLine } from "../numbers/test-line";
import { EmailTemplate } from "./email-template";
import { MailboxCard } from "./mailbox";
import { addressSaid, arrivingOn, comesThrough, ON_A_PAGE, RINGS, ringsSaid } from "../numbers/words";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../numbers/numbers.css";

type Channel = "phone" | "whatsapp" | "sms" | "email" | "messenger";

function Section({ tone, icon, title, about, action, onAdd, children }: { tone: string; icon: IconName; title: string; about: string; action: string; onAdd: () => void; children: ReactNode }): ReactNode {
  return (
    <section className={`num-section num-tone-${tone}`} aria-label={title}>
      <header className="num-section-head">
        <span className="num-section-mark" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
        <span className="num-section-words">
          <span className="num-section-title">{title}</span>
          <span className="num-section-about">{about}</span>
        </span>
        <button type="button" className="cfg-save num-add" onClick={onAdd}>
          <Icon name="plus" size={12} />
          {action}
        </button>
      </header>
      {children}
    </section>
  );
}

// Where a route opens on its own page: a mailbox on Mailboxes, a Page on Messenger & Instagram, any other on Numbers.
function pathOf(one: NumberRow): string {
  const at = encodeURIComponent(one.route.number ?? "");
  if (one.route.channel === "email") return `/mailboxes/${at}`;
  if (ON_A_PAGE.has(one.route.channel)) return `/social/${at}/${one.route.channel}`;
  return `/numbers/${at}${one.route.channel === "phone" ? "" : `/${one.route.channel}`}`;
}

export function ChannelsTab({ agent }: { agent: string }): ReactNode {
  const { agents } = useOrg();
  const { rows, carriers, catalog, refused, reread } = useNumbers();
  const [adding, setAdding] = useState<Channel | null>(null);
  const stopAdding = useCallback(() => setAdding(null), []);
  const mine = (rows ?? []).filter((one) => one.route.agent === agent);
  const read = rows !== null;

  const row = (one: NumberRow): ReactNode => (
    <Link key={`${one.route.number}:${one.route.channel}`} to={pathOf(one)} className="num-row">
      <span className="num-row-number">{addressSaid(one, carriers)}</span>
      <span className="num-row-through dash-clip">{comesThrough(one, carriers, catalog)}</span>
      <span className="num-row-when">{one.last_call_at == null ? `No ${arrivingOn(one.route.channel)} yet` : `Last ${arrivingOn(one.route.channel)} ${ago(one.last_call_at)}`}</span>
      <span className={`num-rings num-rings-${RINGS[one.rings].mood}`}>{ringsSaid(one.rings, one.route.channel)}</span>
    </Link>
  );
  const of = (channel: Channel): NumberRow[] => mine.filter((one) => one.route.channel === channel);
  const onPages = mine.filter((one) => ON_A_PAGE.has(one.route.channel));

  return (
    <div className="num-channels">
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
      <Section tone="blue" icon="numbers" title="Phone" about={`The numbers that ring ${agent} in ${WORLD}.`} action="Add a number" onAdd={() => setAdding("phone")}>
        {!read && <p className="dash-quiet num-none">Reading…</p>}
        {of("phone").map(row)}
        {read && of("phone").length === 0 && <p className="dash-quiet num-none">No number yet.</p>}
        {WORLD === "sandbox" && <TestLine agents={agents.map((one) => one.slug)} agent={agent} />}
      </Section>
      <Section tone="green" icon="chat" title="WhatsApp" about={`The WhatsApp Business numbers whose messages ${agent} answers.`} action="Connect WhatsApp" onAdd={() => setAdding("whatsapp")}>
        {of("whatsapp").map(row)}
        {read && of("whatsapp").length === 0 && <p className="dash-quiet num-none">No WhatsApp number yet.</p>}
      </Section>
      <Section tone="blue" icon="chat" title="SMS" about={`The numbers whose text messages ${agent} answers, from the same number.`} action="Answer SMS" onAdd={() => setAdding("sms")}>
        {of("sms").map(row)}
        {read && of("sms").length === 0 && <p className="dash-quiet num-none">No number answers SMS yet.</p>}
      </Section>
      <Section tone="green" icon="mail" title="Email" about={`The mailboxes whose emails ${agent} answers, each reply set in the org's template.`} action="Connect a mailbox" onAdd={() => setAdding("email")}>
        {of("email").map(row)}
        {of("email").flatMap((one) => carriers.filter((carrier) => carrier.kind === "email" && carrier.account === one.route.account)).map((carrier) => (
          <MailboxCard key={carrier.account} carrier={carrier} onSaved={async () => reread()} />
        ))}
        {read && of("email").length === 0 && <p className="dash-quiet num-none">No mailbox yet. Connect one and every email written to it is answered.</p>}
        {read && of("email").length > 0 && <EmailTemplate />}
      </Section>
      <Section tone="blue" icon="chat" title="Messenger & Instagram" about={`The Facebook Pages, and the Instagram accounts linked to them, whose messages ${agent} answers.`} action="Connect a Page" onAdd={() => setAdding("messenger")}>
        {onPages.map(row)}
        {read && onPages.length === 0 && <p className="dash-quiet num-none">No Facebook Page yet. Connect one and its Messenger and its Instagram are answered.</p>}
      </Section>
      {adding !== null && <AddNumberPanel key={adding} agents={[agent]} agent={agent} channel={adding} onAdded={reread} onClose={stopAdding} />}
    </div>
  );
}
