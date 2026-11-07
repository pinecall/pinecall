/** Finish setting up, at the top of Overview until an org is: how far along it is, the next step with its button, and the rest as chips. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { put, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { JudgingSettingsSchema, LimitsSchema } from "@pinecall/core/wire/rest-org";
import { has, ORG_SCREENS, WORLD } from "../../lib/mode";
import { opens } from "@pinecall/core/scopes";
import { useScopes } from "../../lib/whoami";
import { Button, ButtonLink, Card, Icon, type IconName } from "../../ui";
import { readCarriers, readNumbers } from "../numbers/door";
import { readVendors } from "../providers/door";
import { readMembers } from "../team/door";

interface Step {
  done: boolean;
  name: string;
  icon: IconName;
  /** Why it matters, in a sentence. */
  why: string;
  action?: string;
  to?: string;
  /** Inline action, when the step is done here rather than on another screen. */
  run?: () => Promise<void>;
}

export function Setup({ agents }: { agents: number }): ReactNode {
  const credentials = useCredentials();
  const scopes = useScopes();
  const [steps, setSteps] = useState<Step[] | null>(null);

  const numbers = has(ORG_SCREENS, "numbers") && scopes !== null && opens(scopes, "numbers");
  const team = has(ORG_SCREENS, "team") && scopes !== null && opens(scopes, "team");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (scopes === null) return;
    let gone = false;
    void (async () => {
      const found: Step[] = [
        WORLD === "sandbox"
          ? { done: agents > 0, name: "Make your first agent", icon: "bot", why: "Build one in Studio with no code, or start one you wrote in code.", action: "New agent", to: "/agents" }
          : { done: agents > 0, name: "Put an agent in production", icon: "bot", why: "Deploy one you built in the sandbox, and it answers your customers.", action: "Open Agents", to: "/agents" },
      ];
      // A call runs on the org's own key for a vendor, else on one the box lends; with neither it is refused.
      const [limits, vendors] = await Promise.all([
        read(credentials, "/v1/limits").then((answer) => LimitsSchema.parse(answer), () => null),
        readVendors(credentials).catch(() => [] as string[]),
      ]);
      if (limits !== null) {
        const keyed = vendors.length > 0 || limits.lends === null || limits.lends.length > 0;
        if (!keyed) found.push({ done: false, name: "Add the keys your calls run on", icon: "key", why: "Every call needs a model, speech recognition and a voice. The runtime lends you its keys, or you add your own.", action: "Providers", to: "/providers" });
      }
      const ran = await read(credentials, "/v1/evals/runs", { limit: 1 }).then((answer) => ((answer as { runs?: unknown[] }).runs ?? []).length > 0, () => true);
      found.push({ done: ran, name: "Try it with a simulated caller", icon: "headphones", why: "A model plays a caller in writing, so it costs no call minutes, and the judges score the conversation.", action: "Simulate", to: "/simulations" });
      if (WORLD === "sandbox") {
        const line = await read(credentials, "/v1/line/numbers").then((answer) => answer as { calling?: string[] }, () => null);
        if (line !== null) {
          found.push({ done: (line.calling ?? []).length > 0, name: "Call your agent from your own phone", icon: "phone", why: "Say which phone is yours and your calls reach the agent you are building; nobody else is affected.", action: "Phone testing", to: "/phone" });
        }
      }
      if (numbers) {
        const [accounts, routes] = await Promise.all([readCarriers(credentials).catch(() => []), readNumbers(credentials).catch(() => [])]);
        found.push({ done: accounts.length > 0, name: "Connect your phone provider", icon: "plug", why: "A Twilio account, so numbers you own can reach your agents. Buying a number does not need one.", action: "Connect", to: "/numbers?add=" });
        const pointed = routes.filter((one) => one.route.number !== null).length;
        found.push({ done: pointed > 0, name: pointed > 1 ? `${pointed} numbers answer with an agent` : "Get a phone number for an agent", icon: "route", why: "Buy one here, or bring one you own, and say which agent answers it.", action: "Add a number", to: "/numbers" });
      }
      // Any call reader can read judging; enabling it needs the `usage` scope.
      const judging = await read(credentials, "/v1/org/judging").then((answer) => JudgingSettingsSchema.parse(answer), () => null);
      if (judging !== null && scopes !== null && scopes.includes("usage")) {
        found.push({
          done: judging.on,
          name: "Have every call scored by a judge",
          icon: "scale",
          why: "After each call a judge checks it against your rules, so you find the bad ones without listening.",
          action: "Turn on",
          run: async () => {
            // The PUT is whole: the model the org chose is sent back as it stands.
            await put(credentials, "/v1/org/judging", { on: true, model: judging.model ?? null });
            setTick((now) => now + 1);
          },
        });
      }
      if (team) {
        const members = await readMembers(credentials).catch(() => []);
        found.push({ done: members.filter((one) => one.status !== "disabled").length > 1, name: "Invite your team", icon: "users", why: "Teammates can read calls, listen in and take over from the console.", action: "Invite", to: "/team" });
      }
      if (!gone) setSteps(found);
    })();
    return () => {
      gone = true;
    };
  }, [credentials, numbers, team, scopes, tick, agents]);

  if (steps === null || steps.length === 0 || steps.every((step) => step.done)) return null;
  const done = steps.filter((step) => step.done).length;
  const next = steps.find((step) => !step.done);
  return (
    <Card>
      <div className="ovw-setup">
        <div className="ovw-setup-head">
          <span className="ovw-setup-title">Finish setting up</span>
          <span className="ovw-setup-count">
            {done} of {steps.length}
          </span>
          <span className="ovw-setup-bar" aria-hidden>
            <span style={{ width: `${String(Math.round((done / steps.length) * 100))}%` }} />
          </span>
          <Link to="/welcome" className="ovw-setup-guide">
            Open the guide
          </Link>
        </div>
        {next !== undefined && (
          <div className="ovw-setup-next">
            <span className="ovw-setup-icon">
              <Icon name={next.icon} size={18} />
            </span>
            <span className="ovw-setup-said">
              <span className="ovw-setup-name">{next.name}</span>
              <span className="ovw-setup-why">{next.why}</span>
            </span>
            <Act step={next} primary />
          </div>
        )}
        <div className="ovw-setup-rest">
          {steps
            .filter((step) => step !== next)
            .map((step) => (
              <Act key={step.name} step={step} />
            ))}
        </div>
      </div>
    </Card>
  );
}

/** A step's way forward: the next step's button, or one chip among the rest — ticked when done. */
function Act({ step, primary = false }: { step: Step; primary?: boolean }): ReactNode {
  if (primary) {
    if (step.run !== undefined)
      return (
        <Button kind="primary" onClick={() => void step.run?.()}>
          {step.action}
        </Button>
      );
    return (
      <ButtonLink kind="primary" to={step.to ?? "/"}>
        {step.action}
      </ButtonLink>
    );
  }
  const chip = (
    <>
      <span className={step.done ? "ovw-chip-mark ovw-chip-mark-done" : "ovw-chip-mark"}>{step.done && <Icon name="tick" size={11} />}</span>
      {step.name}
    </>
  );
  if (step.done) return <span className="ovw-chip ovw-chip-done">{chip}</span>;
  if (step.run !== undefined)
    return (
      <button type="button" className="ovw-chip" title={step.why} onClick={() => void step.run?.()}>
        {chip}
      </button>
    );
  return (
    <Link to={step.to ?? "/"} className="ovw-chip" title={step.why}>
      {chip}
    </Link>
  );
}
