/** Step: a phone number for the agent. A new org has none: three ways to get one, each opening Numbers at that step. */

import { useEffect, useState, type ReactNode } from "react";

import { prettyNumber } from "@pinecall/core/calls";
import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { inTheWorld } from "../../lib/mode";

/** A row of `GET /v1/line/numbers`: production's numbers, read from either world. */
export interface Routed {
  number: string;
  agent: string;
}

const WAYS = [
  { id: "buy", name: "Buy one here", says: "Pick a country and an area code. It answers in seconds, bought on Pinecall's own account.", how: "Easiest" },
  { id: "twilio", name: "Bring one from Twilio", says: "Connect your Twilio account once. Your numbers are listed, and you point one at the agent.", how: "If you have one" },
  { id: "whatsapp", name: "WhatsApp", says: "A number on WhatsApp Business. Messages reach the agent, replies go out from it.", how: "Chat, not voice" },
] as const;

export function useRouted(): Routed[] | null {
  const credentials = useCredentials();
  const [routed, setRouted] = useState<Routed[] | null>(null);
  useEffect(() => {
    let gone = false;
    read(credentials, "/v1/line/numbers").then(
      (answer) => {
        if (!gone) setRouted((answer as { numbers: Routed[] }).numbers);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);
  return routed;
}

export function NumberStep({ routed }: { routed: Routed[] | null }): ReactNode {
  return (
    <>
      <p className="wel-lead">People reach your agent by dialling a number. Your org starts with none; this is where you get one and say which agent answers it.</p>
      {routed !== null && routed.length > 0 && (
        <div className="wel-block">
          <strong>Your org's numbers</strong>
          <div className="wel-numbers">
            {routed.map((one) => (
              <div key={one.number} className="wel-number">
                <span className="wel-number-digits">{prettyNumber(one.number)}</span>
                <span className="wel-number-arrow">→</span>
                <span>{one.agent}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="wel-ways-list">
        {WAYS.map((way) => (
          <a key={way.id} className="wel-way-row" href={inTheWorld("production", `/numbers?add=${way.id}`)}>
            <span className="wel-way-text">
              <strong>{way.name}</strong>
              <span>{way.says}</span>
            </span>
            <span className="wel-way-how">{way.how}</span>
            <span className="wel-way-go">Open →</span>
          </a>
        ))}
      </div>
      <span className="wel-hint">Numbers live in production, where your customers are; the next step is how you test one from the sandbox. You can get the number later and go on.</span>
    </>
  );
}
