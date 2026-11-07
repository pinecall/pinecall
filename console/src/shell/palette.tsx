/** ⌘K: jump to a screen, an agent, a call the gateway finds by what was typed, or a call id pasted whole. */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { isLive, whoOn } from "@pinecall/core/calls";
import { floorMoved, matches, useServerSearch } from "@pinecall/core/calls-search";
import type { SessionLine } from "@pinecall/core/wire/rest";
import type { HeldAgent } from "@pinecall/core/wire/rest-org";

import { ago, lettersFor, webVisitor } from "../lib/format";
import { useOrg } from "../lib/org";
import { useScopes } from "../lib/whoami";
import { Avatar, Dot, Icon, Pill } from "../ui";
import { agentHits, callHits, matching, screenHits, type Hit } from "./palette-hits";

// A call id as the log names one: whatever a person pasted from a terminal or a link.
const A_CALL = /^call_[\w+-]{6,}$/;

const MOST = 40;
const RECENT = 6;
// The gateway is asked once there is a word to ask with; one letter would match every call.
const ASK_FROM = 2;

export function Palette({ agent, onClose }: { agent: string; onClose: () => void }): ReactNode {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const { agents, lines, operator, limits } = useOrg();
  const scopes = useScopes();
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    input.current?.focus();
  }, []);

  const words = query.trim();
  const asking = words.length >= ASK_FROM && !A_CALL.test(words);
  // With an agent in view the calls are its own, opened under its path so it stays in view; with
  // every agent in view they are the org's. The gateway searches every call it keeps, not only the
  // page the floor holds; a gateway that cannot (no `total` in its answer) leaves the search to the
  // rows held, as the calls screen does.
  const own = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const base = agent === "" ? "/calls" : `/a/${encodeURIComponent(agent)}/calls`;
  const found = useServerSearch(agent, { query: words, agent: "", channel: "" }, 1, floorMoved(own), asking).found;

  const hits = useMemo((): Hit[] => {
    const all: Hit[] = [];
    if (A_CALL.test(words)) {
      const held = lines.find((one) => one.call === words);
      all.push(held !== undefined ? { kind: "call", group: "Calls", line: held, to: `/calls/${words}` } : { kind: "screen", group: "Open", icon: "external", label: words, where: "a call, by its id", to: `/calls/${words}` });
    }
    const here = agent === "" ? (agents[0]?.slug ?? "") : agent;
    const still = screenHits({ scopes, billed: limits?.billing_url != null, operator: operator === true, agent: here, inView: agent !== "" });
    if (words === "") return [...still, ...agentHits(agents), ...callHits(own.slice(0, RECENT), "Recent calls", base)].slice(0, MOST);
    const calls = found !== null ? found.rows : own.filter((line) => matches(line, words));
    return [...all, ...matching([...still, ...agentHits(agents)], words), ...callHits(calls, "Calls", base)].slice(0, MOST);
  }, [words, agents, lines, own, base, agent, scopes, operator, limits, found]);

  useEffect(() => setCursor(0), [words]);
  // The row the arrows are on stays in view. Braced: an effect's return is its cleanup, and React
  // throws on a value that is neither a function nor undefined.
  useEffect(() => {
    list.current?.querySelector(".palette-item-on")?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

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
          <Icon name="search" size={18} />
          <input
            ref={input}
            className="palette-input"
            placeholder="Search a screen, an agent, a call id, a number or an outcome"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={keys}
          />
          <button type="button" className="palette-kbd" onClick={onClose}>
            esc
          </button>
        </div>
        <div className="palette-list" ref={list}>
          {hits.length === 0 && (
            <div className="palette-none">
              <Icon name="search" size={20} />
              <span>Nothing matches “{words}”</span>
              <span className="palette-none-sub">A screen, an agent, a call id, a number, a caller or an outcome.</span>
            </div>
          )}
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
                  {hit.kind === "screen" && <ScreenRow hit={hit} />}
                  {hit.kind === "agent" && <AgentRow held={hit.held} />}
                  {hit.kind === "call" && <CallRow line={hit.line} />}
                  <span className="palette-enter">↵</span>
                </button>
              </div>
            );
          })}
        </div>
        <div className="palette-foot">
          <span>
            <kbd className="palette-kbd">↑</kbd>
            <kbd className="palette-kbd">↓</kbd> move
          </span>
          <span>
            <kbd className="palette-kbd">↵</kbd> open
          </span>
          <span>
            <kbd className="palette-kbd">esc</kbd> close
          </span>
          {asking && found !== null && found.total > 0 && (
            <span className="palette-foot-count">
              {found.total === 1 ? "1 call" : `${found.total} calls`}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/** A screen: its row's icon on a tile, its name, and the row it is a tab of. */
function ScreenRow({ hit }: { hit: Hit & { kind: "screen" } }): ReactNode {
  return (
    <>
      <span className="palette-tile">
        <Icon name={hit.icon} size={15} />
      </span>
      <span className="palette-text">
        <span className="palette-label ui-clip">{hit.label}</span>
        {hit.where !== "" && <span className="palette-sub ui-clip">{hit.where}</span>}
      </span>
    </>
  );
}

/** An agent: its initials, its slug, what it answers on, and whether Studio holds it. */
function AgentRow({ held }: { held: HeldAgent }): ReactNode {
  return (
    <>
      <Avatar name={held.slug} size={28} />
      <span className="palette-text">
        <span className="palette-label ui-clip">{held.slug}</span>
        <span className="palette-sub ui-clip">{held.channels.length === 0 ? "no channel yet" : held.channels.join(" · ")}</span>
      </span>
      <span className="palette-aside">
        {held.kind === "studio" && (
          <Pill tone="violet" small>
            Studio
          </Pill>
        )}
      </span>
    </>
  );
}

/** A call: who was on it, what came of it, which agent took it, and when — live ones say so. */
function CallRow({ line }: { line: SessionLine }): ReactNode {
  const who = whoOn(line, webVisitor);
  const live = isLive(line);
  return (
    <>
      <Avatar name={who} letters={lettersFor(line.caller?.name, line.direction === "outbound" ? line.to : line.from)} size={28} round />
      <span className="palette-text">
        <span className="palette-label ui-clip">
          {who}
          <span className="palette-agent"> · {line.agent}</span>
        </span>
        <span className="palette-sub ui-clip">{line.outcome ?? (live ? "on the line now" : "nothing was said")}</span>
      </span>
      <span className="palette-aside">
        {live ? (
          <span className="ui-live">
            <Dot tone="green" small /> live
          </span>
        ) : (
          <>
            <Icon name={line.channel === "phone" ? "phone" : "chat"} size={13} />
            {ago(line.started_at)}
          </>
        )}
      </span>
    </>
  );
}
