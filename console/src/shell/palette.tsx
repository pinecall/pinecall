/** ⌘K: jump to a screen, an agent, a call the floor has listed, or a call id pasted whole. */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { AGENT_SCREENS, BOX_SCREENS, ORG_SCREENS, screensOf, WORLD } from "../lib/mode";
import { useOrg } from "../lib/org";
import { opens } from "@pinecall/core/scopes";
import { useScopes } from "../lib/whoami";
import { Icon } from "../ui";

interface Hit {
  group: string;
  label: string;
  sub: string;
  to: string;
}

// A call id as the log names one: whatever a person pasted from a terminal or a link.
const A_CALL = /^call_[\w+-]{6,}$/;

const MOST = 40;

export function Palette({ agent, onClose }: { agent: string; onClose: () => void }): ReactNode {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const { agents, lines, operator } = useOrg();
  const scopes = useScopes();
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);

  const hits = useMemo((): Hit[] => {
    const open = (key: string): boolean => scopes === null || opens(scopes, key);
    const words = query.trim().toLowerCase();
    const all: Hit[] = [];
    if (A_CALL.test(query.trim())) {
      const line = lines.find((one) => one.call === query.trim());
      all.push({ group: "Open", label: query.trim(), sub: line?.agent ?? "by its id", to: `/calls/${query.trim()}` });
    }
    for (const screen of screensOf(ORG_SCREENS).filter((one) => open(one.key))) {
      all.push({ group: "Screens", label: screen.name, sub: "", to: `/${screen.path}` });
    }
    for (const screen of screensOf(BOX_SCREENS, WORLD, operator === true)) {
      all.push({ group: "Box", label: screen.name, sub: "", to: `/${screen.path}` });
    }
    for (const held of agents) {
      all.push({ group: "Agents", label: held.slug, sub: held.channels.join(" · "), to: `/a/${held.slug}/overview` });
    }
    const here = agent === "" ? agents[0]?.slug : agent;
    if (here !== undefined) {
      for (const screen of screensOf(AGENT_SCREENS).filter((one) => open(one.key))) {
        all.push({ group: `${here}`, label: screen.name, sub: here, to: `/a/${here}/${screen.path}` });
      }
    }
    for (const line of lines) {
      const who = line.caller?.name ?? line.from ?? "";
      all.push({ group: "Calls", label: line.call, sub: [line.agent, line.channel, who, line.outcome].filter(Boolean).join(" · "), to: `/calls/${line.call}` });
    }
    if (words === "") return all.filter((hit) => hit.group !== "Calls").slice(0, MOST);
    return all.filter((hit) => `${hit.label} ${hit.sub}`.toLowerCase().includes(words)).slice(0, MOST);
  }, [query, agents, lines, agent, scopes, operator]);

  useEffect(() => setCursor(0), [query]);

  const go = (hit: Hit | undefined): void => {
    if (hit === undefined) return;
    onClose();
    void navigate(hit.to);
  };

  const keys = (event: React.KeyboardEvent): void => {
    if (event.key === "Escape") onClose();
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((at) => Math.min(hits.length - 1, at + 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((at) => Math.max(0, at - 1));
    }
    if (event.key === "Enter") go(hits[cursor]);
  };

  let last = "";
  return (
    <div className="palette-veil" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-label="Search" onMouseDown={(event) => event.stopPropagation()}>
        <div className="palette-input-row">
          <Icon name="search" size={16} />
          <input
            ref={input}
            className="palette-input"
            placeholder="Search a screen, an agent, a call id, a number or an outcome"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={keys}
          />
        </div>
        <div className="palette-list">
          {hits.length === 0 && <div className="palette-none">Nothing here matches — the conversations searched are the ones the org's list holds.</div>}
          {hits.map((hit, index) => {
            const heading = hit.group !== last ? hit.group : null;
            last = hit.group;
            return (
              <div key={`${hit.group}:${hit.to}`}>
                {heading !== null && <div className="palette-group">{heading}</div>}
                <button
                  type="button"
                  className={index === cursor ? "palette-item palette-item-on" : "palette-item"}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => go(hit)}
                >
                  <span className="ui-clip">{hit.label}</span>
                  {hit.sub !== "" && <span className="palette-item-sub">{hit.sub}</span>}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
