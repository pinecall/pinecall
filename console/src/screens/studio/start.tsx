/** Studio before anything is built in it: what an agent here is made of, step by step, and the one move that starts the first. */

import type { ReactNode } from "react";

import { Icon, type IconName } from "../../ui";

const STEPS: readonly { icon: IconName; title: string; said: string }[] = [
  { icon: "words", title: "Write its instructions", said: "Who it is, what it knows, how it talks on the phone." },
  { icon: "chat", title: "Set the greeting", said: "The first thing a caller hears when it picks up." },
  { icon: "plug", title: "Give it tools", said: "Requests to your systems: book, look up, send." },
  { icon: "mic", title: "Try it", said: "Type or talk to it in the sandbox, or let a model play a caller." },
  { icon: "zap", title: "Deploy", said: "One click and production answers with it." },
];

export function Start({ move, note }: { move: ReactNode; note: string }): ReactNode {
  return (
    <section className="sto-start" aria-label="Build your first agent">
      <div className="sto-start-top">
        <span className="sto-start-mark" aria-hidden>
          <Icon name="bot" size={26} />
        </span>
        <span className="sto-start-words">
          <span className="sto-start-title">Build your first agent</span>
          <span className="sto-start-said">{note}</span>
        </span>
        {move}
      </div>
      <ol className="sto-start-steps">
        {STEPS.map((step, at) => (
          <li key={step.title} className="sto-start-step">
            <span className="sto-start-icon" aria-hidden>
              <Icon name={step.icon} size={17} />
            </span>
            <span className="sto-start-num">Step {at + 1}</span>
            <span className="sto-start-name">{step.title}</span>
            <span className="sto-start-step-said">{step.said}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
