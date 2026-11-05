/** Step: a phone number of the org's own. A new org has none: three ways to get one, each opening Numbers at that step. */

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
  { id: "twilio", name: "Bring one from Twilio", says: "Connect your Twilio account once. Your numbers are listed, and you point one at the agent.", how: "If you have one" },
  { id: "buy", name: "Buy one here", says: "Pick a country and an area code. It answers in seconds, bought on Pinecall's own account.", how: "Easiest" },
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

/** `buys`: whether the org may buy a number on Pinecall's account; false on the free plan, null while unknown. */
export function NumberStep({ routed, buys }: { routed: Routed[] | null; buys: boolean | null }): ReactNode {
  return (
    <>
      <p className="wel-lead">
        Customers reach your agent by dialling a number of your own, in production. Your org starts with none; this is where you get one and say which agent answers it. You can do
        this later and go on.
      </p>
      {routed !== null && routed.length > 0 && (
        <div className="wel-block">
          <strong>Your org&apos;s numbers</strong>
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
              <span>{way.id === "buy" && buys === false ? "With a paid plan: pick a country and an area code, and it answers in seconds." : way.says}</span>
            </span>
            <span className="wel-way-how">{way.id === "buy" && buys === false ? "With a plan" : way.how}</span>
            <span className="wel-way-go">Open →</span>
          </a>
        ))}
      </div>
      <span className="wel-hint">
        A number of your own lives in production, where your customers are; to test it from your phone, the step before applies to it too: a call from your mobile reaches your
        sandbox copy.
      </span>
    </>
  );
}
