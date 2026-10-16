/** Layout shared by the sign-in cards: logo, form, footer, and a product illustration. */

import type { ReactNode } from "react";

import "../../ui/ui.css";
import "./login.css";

export function WayIn({ children, foot }: { children: ReactNode; foot?: ReactNode | undefined }): ReactNode {
  return (
    <div className="login">
      <div className="login-side">
        <img className="login-logo login-logo-daylight" src="/pinecall-logo.png" alt="Pinecall" />
        <img className="login-logo login-logo-dark" src="/pinecall-logo-dark.png" alt="Pinecall" />
        <div className="login-form">{children}</div>
        <p className="login-foot">{foot ?? <>Working from a terminal? Run <span className="login-command">pinecall link</span> in your project's folder.</>}</p>
      </div>
      <Showcase />
    </div>
  );
}

const ROWS: readonly { initials: string; tint: string; name: string; line: string; channel: string }[] = [
  { initials: "DK", tint: "violet", name: "Dana Keller", line: "Booked · Friday 2 PM, work order #SO-2026-PL-0060", channel: "phone" },
  { initials: "TS", tint: "pink", name: "Tim Stacy", line: "Quoted the fifteen dollar dispatch fee", channel: "web" },
  { initials: "AR", tint: "green", name: "Ana Ruiz", line: "Callback promised within the hour", channel: "whatsapp" },
];

/** Static illustration of the inbox; not real data. */
function Showcase(): ReactNode {
  return (
    <div className="login-show" aria-hidden>
      <div className="login-show-words">
        <h2 className="login-show-title">Every conversation your company has, in one place.</h2>
        <p className="login-show-lede">Web, WhatsApp and phone land in the same inbox — with the transcript, the outcome and the cost on every row.</p>
      </div>
      <div className="login-show-card">
        <div className="login-show-head">
          <span className="ui-dot ui-dot-green" />
          <span className="login-show-today">Today</span>
          <span className="login-show-count">137 conversations</span>
        </div>
        {ROWS.map((row) => (
          <div key={row.name} className="login-show-row">
            <span className={`ui-avatar ui-avatar-26 ui-tint-${row.tint}`}>{row.initials}</span>
            <div className="ui-row-main">
              <div className="login-show-name">{row.name}</div>
              <div className="login-show-line">{row.line}</div>
            </div>
            <span className="login-show-channel">{row.channel}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
