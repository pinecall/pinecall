/** Corner pop-ups for new calls and handoff requests, linking to the live call. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

import { elapsed, wantsAPerson, whoOn } from "@pinecall/core/calls";
import { useOrg } from "../lib/org";
import { webVisitor } from "../lib/format";
import { isOurs } from "../lib/ours";
import "./ringing.css";

// Newest on top.
const AT_MOST = 3;
const ENDED_STAYS_MS = 5000;

interface Notice {
  call: string;
  line: SessionLine;
  ended: boolean;
  /** The agent is asking for a person, rather than a new call arriving. */
  asked: boolean;
}

/**
 * A call live now but not on the previous floor read is new. Calls already live when the page
 * opened never pop.
 */
export function Ringing(): ReactNode {
  const { live, lines } = useOrg();
  const navigate = useNavigate();
  const where = useLocation().pathname;
  const known = useRef<Set<string> | null>(null);
  // Asks already shown, so re-reads of the floor don't pop them again.
  const asking = useRef<Set<string>>(new Set());
  const [notices, setNotices] = useState<Notice[]>([]);
  const now = useNow(notices.length > 0);

  useEffect(() => {
    // First read: baseline only.
    if (known.current === null) {
      if (lines.length === 0 && live.length === 0) return;
      known.current = new Set(live.map((line) => line.call));
      return;
    }
    const seen = known.current;
    // Skip calls this tab started (Talk, Chat, widget preview).
    const arrived = live.filter((line) => !seen.has(line.call) && !isOurs(line.call));
    live.forEach((line) => seen.add(line.call));
    arrived.forEach((line) => seen.add(line.call));
    // Asks for a person pop even on calls that are not new.
    const wanted = live.filter((line) => wantsAPerson(line) && !asking.current.has(line.call));
    wanted.forEach((line) => asking.current.add(line.call));
    live.filter((line) => !wantsAPerson(line)).forEach((line) => asking.current.delete(line.call));
    setNotices((shown) => {
      const refreshed = shown
        .map((notice) => {
          const current = lines.find((line) => line.call === notice.call);
          return current === undefined ? notice : { ...notice, line: current, ended: !current.live };
        })
        // Close an ask once someone takes it.
        .filter((notice) => !notice.asked || notice.ended || wantsAPerson(notice.line));
      const fresh = [
        ...wanted.map((line) => ({ call: line.call, line, ended: false, asked: true })),
        ...arrived.map((line) => ({ call: line.call, line, ended: false, asked: false })),
      ];
      const kept = refreshed.filter((notice) => !fresh.some((one) => one.call === notice.call && one.asked === notice.asked));
      return [...fresh, ...kept].slice(0, AT_MOST);
    });
  }, [live, lines]);

  useEffect(() => {
    if (!notices.some((notice) => notice.ended)) return;
    const later = window.setTimeout(() => setNotices((shown) => shown.filter((notice) => !notice.ended)), ENDED_STAYS_MS);
    return () => window.clearTimeout(later);
  }, [notices]);

  const close = (call: string): void => setNotices((shown) => shown.filter((notice) => notice.call !== call));
  // No window for the call already on screen.
  const shown = notices.filter((notice) => where !== `/calls/${notice.call}`);
  if (shown.length === 0) return null;

  return (
    <div className="ring-stack" role="region" aria-label="Calls coming in" aria-live="polite">
      {shown.map((notice) => (
        <div key={`${notice.call}${notice.asked ? "-asked" : ""}`} className={ground(notice)}>
          <button
            type="button"
            className="ring-body"
            onClick={() => {
              close(notice.call);
              void navigate(`/calls/${notice.call}`);
            }}
          >
            <span className={notice.ended ? "ring-icon ring-icon-ended" : notice.asked ? "ring-icon ring-icon-asked" : "ring-icon"} aria-hidden>
              {notice.asked && !notice.ended ? <HandGlyph /> : <PhoneGlyph />}
            </span>
            <span className="ring-words">
              <span className="ring-top">
                <span className="ring-kicker">{kicker(notice)}</span>
                {!notice.ended && <span className="ring-watch">{notice.asked ? "Take the line →" : "Watch live →"}</span>}
              </span>
              <span className="ring-who">{whoOn(notice.line, webVisitor)}</span>
              <span className="ring-sub">
                {notice.asked && notice.line.attention !== null && notice.line.attention !== undefined && `${notice.line.attention.reason} · `}
                {notice.line.agent}
                {notice.line.channel !== null && ` · ${notice.line.channel}`}
                {notice.line.direction === "outbound" && " · outbound"}
                {!notice.ended && notice.line.started_at !== null && ` · ${elapsed(notice.line.started_at, now)}`}
              </span>
            </span>
          </button>
          <button type="button" className="ring-close" aria-label="Dismiss" onClick={() => close(notice.call)}>
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

function ground(notice: Notice): string {
  if (notice.ended) return "ring ring-ended";
  return notice.asked ? "ring ring-asked" : "ring";
}

function kicker(notice: Notice): string {
  if (notice.ended) return "Call ended";
  if (notice.asked) return "Wants a person";
  if (notice.line.direction === "outbound") return "Calling out";
  if (notice.line.channel === "web") return "New conversation";
  if (notice.line.channel === "whatsapp") return "New WhatsApp chat";
  return notice.line.status === "active" ? "New call · answered" : "New call ringing";
}

function HandGlyph(): ReactNode {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a2 2 0 0 1 2 2v7M8 13V6a2 2 0 1 1 4 0M16 13V7a2 2 0 1 1 4 0v7a7 7 0 0 1-7 7h-1a7 7 0 0 1-7-7v-2a2 2 0 1 1 4 0" />
    </svg>
  );
}

function PhoneGlyph(): ReactNode {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
    </svg>
  );
}

// Ticks the elapsed-time labels independently of floor updates.
function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!ticking) return;
    const tick = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(tick);
  }, [ticking]);
  return now;
}
