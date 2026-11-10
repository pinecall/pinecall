/** The figures a person checks first: how long callers wait, what the judges held, how many calls, what they cost, each against the window before. */

import type { ReactNode } from "react";

import { change, count, money, percent } from "../lib/format";
import { beforeSaid, lengthSaid, took, type Totals } from "./fold";

type Mood = "good" | "bad" | "calm";

interface Figure {
  label: string;
  value: string;
  moved: string;
  mood: Mood;
  fact: string;
}

// Under this a wait reads the same to a caller.
const STEADY_S = 0.05;

function figuresOf(now: Totals, before: Totals | null, days: number): Figure[] {
  const against = `against ${beforeSaid(days)}`;
  const nothing = before === null ? "" : `Nothing to compare with in ${beforeSaid(days)}`;

  const faster = now.answer === null || before === null || before.answer === null ? null : before.answer - now.answer;
  const heldNow = now.judged === 0 ? null : now.held / now.judged;
  const heldBefore = before === null || before.judged === 0 ? null : before.held / before.judged;
  const points = heldNow === null || heldBefore === null ? null : Math.round((heldNow - heldBefore) * 100);
  const moved = before === null ? null : change(now.calls, before.calls);
  const cost = before === null || before.spend === 0 ? null : change(now.spend, before.spend);
  const signed = (share: number): string => `${share >= 0 ? "+" : "−"}${percent(Math.abs(share))}`;

  return [
    {
      label: "Time to answer",
      value: now.answer === null ? "—" : took(now.answer),
      moved: faster === null ? nothing : Math.abs(faster) < STEADY_S ? `Steady ${against}` : `${took(Math.abs(faster))} ${faster > 0 ? "faster" : "slower"} than ${beforeSaid(days)}`,
      mood: faster === null || Math.abs(faster) < STEADY_S ? "calm" : faster > 0 ? "good" : "bad",
      fact: now.firstToken === null ? "The model's first word was not timed" : `The model's first word in ${took(now.firstToken)}`,
    },
    {
      label: "Held by the judges",
      value: heldNow === null ? "—" : percent(heldNow),
      moved: points === null ? (now.judged === 0 ? "No call was judged" : nothing) : points === 0 ? `Steady ${against}` : `${points > 0 ? "+" : "−"}${Math.abs(points)} points ${against}`,
      mood: points === null || points === 0 ? "calm" : points > 0 ? "good" : "bad",
      fact: `${count(now.held)} of ${count(now.judged)} verdicts`,
    },
    {
      label: "Calls",
      value: count(now.calls),
      moved: moved === null ? nothing : Math.round(moved * 100) === 0 ? `Steady ${against}` : `${signed(moved)} ${against}`,
      mood: "calm",
      fact: now.length === null ? "No call has ended" : `${lengthSaid(now.length)} long on average`,
    },
    {
      label: "Spend",
      value: money(now.spend),
      moved: cost === null ? nothing : Math.round(cost * 100) === 0 ? `Steady ${against}` : `${signed(cost)} ${against}`,
      mood: "calm",
      fact: now.calls === 0 ? "No call to price" : `${money(now.spend / now.calls)} a call`,
    },
  ];
}

/** `before` is null until the window before is read: the figures stand without their comparison meanwhile. */
export function Hero({ now, before, days }: { now: Totals; before: Totals | null; days: number }): ReactNode {
  return (
    <section className="dash-card ob-hero" aria-label="The window at a glance">
      {figuresOf(now, before, days).map((one) => (
        <div key={one.label} className="ob-figure">
          <span className="dash-eyebrow">{one.label}</span>
          <span className="dash-big ob-figure-value">{one.value}</span>
          <span className={one.mood === "calm" ? "ob-figure-moved dash-quiet" : `ob-figure-moved dash-mood-${one.mood}`}>{one.moved}</span>
          <span className="dash-quiet">{one.fact}</span>
        </div>
      ))}
    </section>
  );
}
