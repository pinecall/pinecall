/** Where the fix of a case belongs: the settings, a version and no deploy, or the code, a pull request. */

import type { ReactNode } from "react";

import { ButtonLink } from "../../ui";
import type { EvalCase } from "./door";
import { Section } from "./section";

// What a judge's reason points at, and the home of the block that says it (the prompt's own page).
const IN_THE_SETTINGS = [
  ["a price, an hour, a policy, what to say when asked", "Knowledge"],
  ["how the call opens or ends", "the greeting, the hang-up"],
  ["a fact kept, or one that should never be", "the memory policy"],
  ["the model guessed, cut the caller off", "the model, turn taking"],
] as const;

const IN_THE_CODE = [
  ["did the wrong thing in this stage", "render(), the view"],
  ["used a tool for the wrong thing, or did not wait for a yes", "the tool's docstring"],
  ["the same slip everywhere: tone, inventing, two questions at once", "the class docstring"],
] as const;

export function FixIt({ agent, kept }: { agent: string; kept: EvalCase }): ReactNode {
  const configure = `/a/${encodeURIComponent(agent)}/configure`;
  return (
    <Section title="Fix it where it belongs">
      <div className="cs-fix">
        <div className="cs-fix-half">
          <h3 className="cs-fix-title">In the settings — a new version, no deploy</h3>
          <dl className="cs-fix-rows">
            {IN_THE_SETTINGS.map(([when, where]) => (
              <div key={when}>
                <dt>{when}</dt>
                <dd>{where}</dd>
              </div>
            ))}
          </dl>
          <p className="cs-fix-how">
            Saved in your own corner, nobody else hears it. Run the case on that version below; once it holds, apply it to the team, then to
            production.
          </p>
          <ButtonLink size="sm" to={configure}>
            Open Configure
          </ButtonLink>
        </div>
        <div className="cs-fix-half">
          <h3 className="cs-fix-title">In the code — a pull request</h3>
          <dl className="cs-fix-rows">
            {IN_THE_CODE.map(([when, where]) => (
              <div key={when}>
                <dt>{when}</dt>
                <dd>{where}</dd>
              </div>
            ))}
          </dl>
          <p className="cs-fix-how">In the agent's directory, play it on every save, then put it in the repository so the pull request carries it:</p>
          <pre className="cs-cmd">{`pinecall test --case ${kept.name} --watch\npinecall cases pull ${kept.name}`}</pre>
        </div>
      </div>
    </Section>
  );
}
