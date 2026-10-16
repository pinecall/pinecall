/** The welcome guide a new org lands on: one step, one thing, from nothing to an agent answering a phone call. */

import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { useLimits } from "../../lib/limits";
import { inTheWorld, WORLD } from "../../lib/mode";
import { useOrg } from "../../lib/org";
import { markWelcomed } from "../../lib/preferences";
import { useWhoami } from "../../lib/whoami";
import { Button, Page, TextAction } from "../../ui";
import { NumberStep, useRouted } from "./number-step";
import { PhoneStep } from "./phone-step";
import { SimulateStep } from "./simulate-step";
import { RunStep } from "./run-step";
import { CodeStep, Gives, Ready } from "./steps";
import type { Language } from "./agent-code";
import { TryStep } from "./try-step";
import "./welcome.css";

const TITLES = ["Welcome", "What an agent is", "Run it on your computer", "Talk to it", "A simulated caller", "A phone number", "Call it from your mobile", "Go live"] as const;

/** The step that gets the agent running: the one a later step sends a person back to. */
const RUN = 2;

/** `/welcome`: reached on a first visit, and from Overview's Get started at any time; always in the sandbox. */
export function Welcome(): ReactNode {
  const navigate = useNavigate();
  const limits = useLimits();
  const { agents } = useOrg();
  const routed = useRouted();
  const first = (useWhoami()?.name ?? "").split(" ")[0] ?? "";
  const [step, setStep] = useState(0);
  const [language, setLanguage] = useState<Language>("typescript");
  const last = step === TITLES.length - 1;

  // The guide is the sandbox's: the sample it runs, the chat and the simulation all belong there, so
  // production's console hands it over rather than run a first try where customers call.
  useEffect(() => {
    if (WORLD === "production") window.location.replace(inTheWorld("sandbox", "/welcome"));
  }, []);

  const leave = (): void => {
    markWelcomed();
    navigate("/", { replace: true });
  };

  const body = [
    <Gives key="gives" limits={limits} world={WORLD} />,
    <CodeStep key="code" language={language} onLanguage={setLanguage} />,
    <RunStep key="run" language={language} agents={agents} />,
    <TryStep key="try" agents={agents} onBack={() => setStep(RUN)} />,
    <SimulateStep key="simulate" agents={agents} onBack={() => setStep(RUN)} />,
    <NumberStep key="number" routed={routed} />,
    <PhoneStep key="phone" routed={routed} running={agents.length > 0} />,
    <Ready key="ready" world={WORLD} />,
  ][step];

  return (
    <Page width={760}>
      <div className="wel">
        <div className="wel-progress" aria-label={`Step ${step + 1} of ${TITLES.length}`}>
          {TITLES.map((title, index) => (
            <span key={title} className={index < step ? "wel-bar wel-bar-done" : index === step ? "wel-bar wel-bar-now" : "wel-bar"} />
          ))}
        </div>
        <div className="wel-count">
          Step {step + 1} of {TITLES.length}
        </div>
        <h1 className="wel-title">{step === 0 && first !== "" ? `Welcome to Pinecall, ${first}` : TITLES[step]}</h1>
        <div className="wel-body">{body}</div>
        <div className="wel-nav">
          {step > 0 && (
            <Button size="md" onClick={() => setStep(step - 1)}>
              Back
            </Button>
          )}
          <Button kind="primary" size="md" onClick={() => (last ? leave() : setStep(step + 1))}>
            {last ? "Go to my Overview" : step === 0 ? "Let's start" : "Next"}
          </Button>
          {!last && <TextAction onClick={leave}>Skip the guide</TextAction>}
        </div>
      </div>
    </Page>
  );
}
