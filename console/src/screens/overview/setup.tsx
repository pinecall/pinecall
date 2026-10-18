/** The first-run guide, at the top of Overview until an org is set up: each step says why, shows the command, and links to its screen. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { put, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { JudgingSettingsSchema, LimitsSchema } from "@pinecall/core/wire/rest-org";
import { has, ORG_SCREENS, WORLD } from "../../lib/mode";
import { opens } from "@pinecall/core/scopes";
import { useScopes } from "../../lib/whoami";
import type { Limits } from "@pinecall/core/wire/rest-org";
import { Card, CardHead } from "../../ui";
import { readCarriers, readNumbers } from "../numbers/door";
import { readVendors } from "../providers/door";
import { readMembers } from "../team/door";

interface Step {
  done: boolean;
  name: string;
  /** Why it matters, in a sentence. */
  why: string;
  /** What to type for it, when it is a command. */
  command?: string;
  action?: string;
  to?: string;
  /** Inline action, when the step is done here rather than on another screen. */
  run?: () => Promise<void>;
}

export function Setup({ agents, limits }: { agents: number; limits: Limits | null }): ReactNode {
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
        { done: agents > 0, name: "Make your first agent", why: "An agent is a class in a folder of yours; this writes one, and its pinecall.json says it runs in your org.", command: "pinecall new front-desk && cd front-desk && pinecall start" },
      ];
      // A call runs on the org's own key for a vendor, else on one the box lends; with neither it is refused.
      const [limits, vendors] = await Promise.all([
        read(credentials, "/v1/limits").then((answer) => LimitsSchema.parse(answer), () => null),
        readVendors(credentials).catch(() => [] as string[]),
      ]);
      if (limits !== null) {
        const keyed = vendors.length > 0 || limits.lends === null || limits.lends.length > 0;
        if (!keyed) found.push({ done: false, name: "Add the keys your calls run on", why: "Every call needs a model, speech recognition and a voice. Pinecall lends you its keys, or you add your own.", action: "Providers", to: "/providers" });
      }
      const ran = await read(credentials, "/v1/evals/runs", { limit: 1 }).then((answer) => ((answer as { runs?: unknown[] }).runs ?? []).length > 0, () => true);
      found.push({ done: ran, name: "Try it with a simulated caller", why: "A model plays a caller in writing, so it costs no call minutes. The judges score the conversation.", command: "pinecall simulate --persona hurried --judge", action: "Simulate", to: "/simulations" });
      if (WORLD === "sandbox") {
        const line = await read(credentials, "/v1/line/numbers").then((answer) => answer as { calling?: string[] }, () => null);
        if (line !== null) {
          found.push({ done: (line.calling ?? []).length > 0, name: "Call your agent from your own phone", why: "Your calls reach the copy running on your computer, and nobody else is affected.", command: "pinecall line from +34600000000 && pinecall start", action: "Phone testing", to: "/phone" });
        }
      }
      if (numbers) {
        const [accounts, routes] = await Promise.all([readCarriers(credentials).catch(() => []), readNumbers(credentials).catch(() => [])]);
        found.push({ done: accounts.length > 0, name: "Connect your phone provider", why: "A Twilio account, so numbers you own can reach your agents. Buying a number does not need one.", action: "Connect", to: "/numbers?add=" });
        const pointed = routes.filter((one) => one.route.number !== null).length;
        found.push({ done: pointed > 0, name: pointed > 1 ? `${pointed} numbers answer with an agent` : "Get a phone number for an agent", why: "Buy one here, or bring one you own, and say which agent answers it.", command: "pinecall numbers buy --country ES --agent front-desk --prod", action: "Add a number", to: "/numbers" });
      }
      // Any call reader can read judging; enabling it needs the `usage` scope.
      const judging = await read(credentials, "/v1/org/judging").then((answer) => JudgingSettingsSchema.parse(answer), () => null);
      if (judging !== null && scopes !== null && scopes.includes("usage")) {
        found.push({
          done: judging.on,
          name: "Have every call scored by a judge",
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
        found.push({ done: members.filter((one) => one.status !== "disabled").length > 1, name: "Invite your team", why: "Teammates can read calls, listen in and take over from the console.", action: "Invite", to: "/team" });
      }
      if (!gone) setSteps(found);
    })();
    return () => {
      gone = true;
    };
  }, [credentials, numbers, team, scopes, tick, agents]);

  if (steps === null || steps.length === 0 || steps.every((step) => step.done)) return null;
  const done = steps.filter((step) => step.done).length;
  const free = limits !== null && limits.minutes.limit !== null ? limits.minutes.limit : null;
  return (
    <Card>
      <CardHead title="Get started" meta={`${done} of ${steps.length} done`} action={<Link to="/welcome">Open the guide</Link>} />
      <div className="ovw-welcome">
        {free === null
          ? "Follow these steps to your first call."
          : `Your ${WORLD === "sandbox" ? "sandbox has" : "production allows"} ${free} call minutes a month, starting again on the 1st (UTC). Written chats and simulations use none. Follow these steps to your first call.`}
      </div>
      <div className="ovw-steps">
        {steps.map((step, index) => (
          <div key={step.name} className={step.done ? "ovw-step ovw-step-finished" : "ovw-step"}>
            <span className={step.done ? "ovw-step-done" : "ovw-step-num"}>{step.done ? "✓" : index + 1}</span>
            <span className="ovw-step-text">
              <span className={step.done ? "ovw-step-name ovw-step-name-done" : "ovw-step-name"}>{step.name}</span>
              {!step.done && <span className="ovw-step-why">{step.why}</span>}
              {!step.done && step.command !== undefined && <code className="ovw-step-command">{step.command}</code>}
            </span>
            {!step.done &&
              step.action !== undefined &&
              (step.run !== undefined ? (
                <button type="button" className="ovw-step-action ovw-step-button" onClick={() => void step.run?.()}>
                  {step.action}
                </button>
              ) : (
                <Link to={step.to ?? "/"} className="ovw-step-action">
                  {step.action}
                </Link>
              ))}
          </div>
        ))}
      </div>
    </Card>
  );
}
