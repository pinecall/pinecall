/** The agent `pinecall new` writes, in each language, as the guide shows it: the class is the whole agent. */

export type Language = "typescript" | "ruby" | "python";

/** The slug `pinecall new` is told in the guide, and the agent its later steps look for. */
export const SLUG = "front-desk";

export const LANGUAGES: readonly { value: Language; label: string; flag: string }[] = [
  { value: "typescript", label: "TypeScript", flag: "" },
  { value: "ruby", label: "Ruby", flag: " --ruby" },
  { value: "python", label: "Python", flag: " --python" },
];

/** The file `pinecall new` writes it to. */
export const FILE: Record<Language, string> = { typescript: "agents/front-desk/agent.tsx", ruby: "agents/front-desk/agent.rb", python: "agents/front-desk/agent.py" };

/** What to read in the code, in the order it appears. */
export const READS: Record<Language, readonly string[]> = {
  typescript: [
    "The comment over the class is the prompt: who the agent is and how it speaks.",
    "A @tool is something it can do. The model calls it when the conversation gets there.",
    "render() is the part of the prompt that changes from one turn to the next.",
  ],
  ruby: [
    "The comment over the class is the prompt: who the agent is and how it speaks.",
    "A tool is something it can do. The model calls it when the conversation gets there.",
    "The view in views/ is the part of the prompt that changes from one turn to the next.",
  ],
  python: [
    "The docstring of the class is the prompt: who the agent is and how it speaks.",
    "A @tool is something it can do. The model calls it when the conversation gets there.",
    "The view in views/ is the part of the prompt that changes from one turn to the next.",
  ],
};

export const CODE: Record<Language, string> = {
  typescript: `import { Agent, tool, type Stages } from "@pinecall/agents";

/**
 * You answer the phone for the business. Short sentences: everything you say is read aloud.
 * You answer what the business's documents say. For anything else you take a message: who is
 * calling and what it is about. You never promise when they will hear back.
 */
export default class FrontDesk extends Agent {
  stage: Stages<"ask" | "done"> = "ask";
  message?: { name: string; about: string };

  /** Writes down the caller's message, once they have said their name and what it is about. */
  @tool({ stage: "ask", pii: ["name"] })
  async takeMessage(name: string, about: string) {
    this.message = { name, about };
    this.stage = "done";
    return this.message;
  }

  override render() {
    return (
      <>
        {this.stage === "ask" && <p>Greet the caller. Answer from the documents, or ask their name and what it is about.</p>}
        {this.message && <p>The message is written down. Tell them it reached the team, say goodbye and hang up.</p>}
      </>
    );
  }
}`,
  ruby: `require "pinecall"

# You answer the phone for the business. Short sentences: everything you say is read aloud.
# You answer what the business's documents say. For anything else you take a message: who is
# calling and what it is about. You never promise when they will hear back.
class FrontDesk < Pinecall::Agent
  stage :ask, :done

  state :message

  # Writes down the caller's message, once they have said their name and what it is about.
  tool stage: :ask, pii: %i[name]
  def take_message(name:, about:)
    self.message = { name:, about: }
    self.stage = :done
    message
  end
end`,
  python: `from typing import Literal

from pinecall import Agent, tool


class FrontDesk(Agent):
    """You answer the phone for the business. Short sentences: everything you say is read aloud.
    You answer what the business's documents say. For anything else you take a message: who is
    calling and what it is about. You never promise when they will hear back.
    """

    stage: Literal["ask", "done"] = "ask"
    message: dict[str, str] | None = None

    @tool(stage="ask", pii=("name",))
    def take_message(self, name: str, about: str) -> dict[str, str]:
        """Writes down the caller's message, once they have said their name and what it is about."""
        self.message = {"name": name, "about": about}
        self.stage = "done"
        return self.message`,
};
