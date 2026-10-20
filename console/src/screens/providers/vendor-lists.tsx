/** The vendors an org runs on, and the others it could bring a key for. */

import { useState, type ReactNode } from "react";

import { ITS_OWN, MODALITIES, NO_PLUGIN, READY, doing, said, type Modality, type Provider } from "../../lib/catalogue";
import { lending, type Lending } from "../../lib/limits";
import { Card, CardHead, Chips, Empty, Pill, TextAction } from "../../ui";

const COLUMNS = "130px minmax(0,1fr) 170px 90px";

/** What a vendor is for, in the words the rest of the console uses. */
export const FOR: Record<Modality, string> = { llm: "Model", stt: "Speech recognition", tts: "Voice" };

const kinds = (one: Provider): string => one.does.map((kind) => FOR[kind]).join(" · ");

/** Whose key a vendor runs on for this org, or null when it runs on none. */
export function source(one: Provider, brought: boolean, lends: string[] | null): { text: string; tone: "green" | "amber" } | null {
  if (brought) return { text: "Your key", tone: "green" };
  if (one.standing !== READY) return null;
  const lent: Lending = lending(lends, one.name);
  if (lent === "all") return { text: "The runtime's key", tone: "green" };
  if (lent === "some") return { text: "The runtime's key, some models", tone: "amber" };
  return null;
}

/** What stops an org using a vendor it has no key for, in one line. */
function missing(one: Provider): string {
  if (one.standing === NO_PLUGIN) return "Not installed on this box";
  if (one.standing === ITS_OWN) return "Needs its own credentials: use the CLI";
  return "Add your key to use it";
}

export function RunningOn({ providers, brought, lends, onGiveBack }: { providers: Provider[]; brought: Set<string>; lends: string[] | null; onGiveBack: (name: string) => void }): ReactNode {
  const running = providers.flatMap((one) => {
    const from = source(one, brought.has(one.name), lends);
    return from === null ? [] : [{ one, from }];
  });
  return (
    <Card>
      <CardHead title="Running your agents" meta="Your agents use these vendors. Your own key is used first." />
      {running.length === 0 ? (
        <Empty>No vendor is available yet. Add your own key below.</Empty>
      ) : (
        running.map(({ one, from }) => (
          <div key={one.name} className="prov-row" style={{ gridTemplateColumns: COLUMNS }}>
            <span className="prov-name">{one.name}</span>
            <span className="prov-kinds">{kinds(one)}</span>
            <Pill tone={from.tone}>{from.text}</Pill>
            <span className="ui-cell-end">
              {brought.has(one.name) && (
                <TextAction danger onClick={() => onGiveBack(one.name)}>
                  Remove
                </TextAction>
              )}
            </span>
          </div>
        ))
      )}
    </Card>
  );
}

const FILTERS = ["all", ...MODALITIES] as const;
type Filter = (typeof FILTERS)[number];

export function OtherVendors({ providers, brought, lends }: { providers: Provider[]; brought: Set<string>; lends: string[] | null }): ReactNode {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const others = providers.filter((one) => source(one, brought.has(one.name), lends) === null);
  const shown = (filter === "all" ? others : doing(others, filter)).slice().sort((one, other) => one.name.localeCompare(other.name));
  return (
    <Card>
      <CardHead
        title="Other vendors"
        meta={`${others.length} more that Pinecall supports. Add your own key above to use one.`}
        action={<TextAction onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</TextAction>}
      />
      {open && (
        <>
          <div className="prov-filter">
            <Chips
              options={FILTERS.map((one) => ({ value: one, label: one === "all" ? "All" : FOR[one] }))}
              value={filter}
              onChange={setFilter}
            />
          </div>
          {shown.map((one) => (
            <div key={one.name} className="prov-row" style={{ gridTemplateColumns: COLUMNS }} title={said(one)}>
              <span className="prov-name">{one.name}</span>
              <span className="prov-kinds">{kinds(one)}</span>
              <span className="prov-kinds">{missing(one)}</span>
              <span />
            </div>
          ))}
        </>
      )}
    </Card>
  );
}
