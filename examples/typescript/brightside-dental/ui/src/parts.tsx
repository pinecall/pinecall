// The page's component for each part Brightside's agents name (../../lib/screen.ts): the agents say what, the page says how.

import type { Parts } from "@pinecall/room/react";
import { useState, type FormEvent, type ReactNode } from "react";

import type { Invoice, Slot, Visit } from "../../lib/clinic.js";

import { usePage } from "./page.js";

const ZONE = "America/Los_Angeles";

function dayOf(day: string): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" });
}

function Stage({ children }: { children?: ReactNode }): ReactNode {
  return <>{children}</>;
}

function Welcome({ patient }: { patient?: string }): ReactNode {
  return (
    <div className="welcome">
      <h2>{patient === undefined ? "Hello." : `Hello, ${patient.split(" ")[0]}.`}</h2>
      <p>Say what you need. Things to try:</p>
      <ul>
        <li>“I need a cleaning next Tuesday.”</li>
        <li>“What do you have on Thursday?”</li>
        <li>“I was charged twice for my cleaning.”</li>
      </ul>
    </div>
  );
}

function Agenda({ slots, picked }: { slots: Slot[]; picked?: string }): ReactNode {
  const page = usePage();
  return (
    <div className="agenda">
      <p className="eyebrow">Open times</p>
      <h2>{slots[0] === undefined ? "" : dayOf(slots[0].day)}</h2>
      <div className="slots">
        {slots.map((slot) => (
          <button key={slot.time} disabled={!page.live} aria-pressed={picked === `${slot.day} ${slot.time}`} onClick={() => page.tell("slot.picked", { day: slot.day, time: slot.time })}>
            <b>{slot.time}</b>
            <small>{slot.with}</small>
          </button>
        ))}
      </div>
      <p className="hint">Say one, or tap it. Nothing is booked until you say yes.</p>
    </div>
  );
}

function Form({ task, asks, fields, refused }: { task: string; asks: string; fields: Record<string, string>; refused?: string }): ReactNode {
  const page = usePage();
  const [given, setGiven] = useState<Record<string, string>>({});
  const give = (event: FormEvent): void => {
    event.preventDefault();
    page.tell("task.give", { task, given: Object.fromEntries(Object.keys(fields).map((field) => [field, given[field] ?? ""])) });
  };
  return (
    <form className="ask" onSubmit={give}>
      <p className="eyebrow">One thing before it is done</p>
      <h2>We need {asks}.</h2>
      {Object.entries(fields).map(([field, what]) => (
        <label key={field}>
          <span>{field}</span>
          <input autoFocus value={given[field] ?? ""} onChange={(event) => setGiven({ ...given, [field]: event.target.value })} placeholder={task === "phone" ? "+1 415 555 0142" : what} disabled={!page.live} />
        </label>
      ))}
      {refused !== undefined && <p className="error">{refused}</p>}
      <button className="primary" disabled={!page.live}>Give it</button>
      <p className="hint">Or just say it: the agent is listening.</p>
    </form>
  );
}

function Ticket({ visit, phone, remindedAt }: { visit: Visit; phone: string; remindedAt: string }): ReactNode {
  const reminder = new Date(remindedAt).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: ZONE });
  return (
    <div className="ticket">
      <div className="stub">
        <p className="eyebrow">Booked · {visit.id}</p>
        <h2>{visit.time}</h2>
        <p className="day">{dayOf(visit.day)}</p>
      </div>
      <dl>
        <div><dt>Patient</dt><dd>{visit.patient}</dd></div>
        <div><dt>With</dt><dd>{visit.with}</dd></div>
        <div><dt>Reminder to</dt><dd>{phone}</dd></div>
      </dl>
      <ol className="timeline">
        <li data-done>Booked on this call</li>
        <li>We call you {reminder}</li>
        <li>Your visit, {visit.time}</li>
      </ol>
    </div>
  );
}

function Invoices({ invoices, about, refundAsked }: { invoices: Invoice[]; about?: string; refundAsked?: string }): ReactNode {
  return (
    <div className="invoices">
      <p className="eyebrow">Billing</p>
      <h2>Your invoices</h2>
      {invoices.length === 0 && <p className="hint">None on file for this caller. Billing will ask for the number the visit was booked with.</p>}
      <ul>
        {invoices.map((invoice) => (
          <li key={invoice.id} data-about={invoice.id === about || undefined}>
            <span className="id">{invoice.id}</span>
            <span className="what">{invoice.what}</span>
            <span className="amount">${invoice.amount.toFixed(2)}</span>
            <span className="badge" data-tone={invoice.id === refundAsked ? "asked" : invoice.paid ? "paid" : "due"}>{invoice.id === refundAsked ? "refund asked" : invoice.paid ? "paid" : "due"}</span>
          </li>
        ))}
      </ul>
      {refundAsked !== undefined && refundAsked !== "" && <p className="hint">The office decides a refund and calls back within one business day.</p>}
    </div>
  );
}

export const PARTS: Parts = { stage: Stage, welcome: Welcome, agenda: Agenda, form: Form, ticket: Ticket, invoices: Invoices };
