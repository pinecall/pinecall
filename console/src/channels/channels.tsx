/** An agent's Channels tab: the phone numbers and the WhatsApp numbers that reach it, each with how it rings, and the way to give it another. */

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
import { comesThrough, RINGS, shown } from "../numbers/words";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../numbers/numbers.css";

type Channel = "phone" | "whatsapp";

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

export function ChannelsTab({ agent }: { agent: string }): ReactNode {
  const { agents } = useOrg();
  const { rows, carriers, catalog, refused, reread } = useNumbers();
  const [adding, setAdding] = useState<Channel | null>(null);
  const stopAdding = useCallback(() => setAdding(null), []);
  const mine = (rows ?? []).filter((one) => one.route.agent === agent);
  const read = rows !== null;

  const row = (one: NumberRow): ReactNode => (
    <Link key={one.route.number} to={`/numbers/${encodeURIComponent(one.route.number ?? "")}`} className="num-row">
      <span className="num-row-number">{shown(one.route.number)}</span>
      <span className="num-row-through dash-clip">{comesThrough(one, carriers, catalog)}</span>
      <span className="num-row-when">{one.last_call_at == null ? "No call yet" : `Last call ${ago(one.last_call_at)}`}</span>
      <span className={`num-rings num-rings-${RINGS[one.rings].mood}`}>{RINGS[one.rings].said}</span>
    </Link>
  );
  const of = (channel: Channel): NumberRow[] => mine.filter((one) => one.route.channel === channel);

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
      {adding !== null && <AddNumberPanel key={adding} agents={[agent]} agent={agent} channel={adding} onAdded={reread} onClose={stopAdding} />}
    </div>
  );
}
