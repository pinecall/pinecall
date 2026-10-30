// {{Title}}: the class is the agent — its state, its tools, and render(), its prompt.

import { Agent, judges, personas, tool, type Stages } from "@pinecall/agents";

// The eight judges Pinecall recommends, on for every call; the agent's own are the files under judges/.
const RECOMMENDED = ["consent", "grounded", "promises", "disclosed", "identified", "honoured-stop", "ended-well", "expected-outcome"];

// What a model in a hurry writes where the caller said nothing: never a message.
const NOTHING_SAID = /^(n\/?a|none|unknown|unspecified|not (specified|given|provided|said)|tbd|-)?$/i;

/**
 * You answer the phone for the business. Short sentences: everything you say is read aloud.
 * You answer what the business's documents say. For anything else you take a message: who is calling
 * and what it is about. You never promise when they will hear back.
 */
export default class {{Class}} extends Agent {
  static judges = judges({ on: RECOMMENDED });
  // Pinecall's callers this agent is tested with, and its own under test/personas/.
  static personas = personas({ on: ["in-a-hurry", "wrong-number"] });

  stage: Stages<"ask" | "done"> = "ask";
  message?: { name: string; about: string } | undefined;

  /**
   * Writes down the caller's message. Call it as soon as the caller has said their name and what the call is
   * about, in that same turn and without reading it back first; never with a blank or a guess.
   */
  @tool({ stage: "ask", pii: ["name"] })
  async takeMessage(name: string, about: string): Promise<{ name: string; about: string }> {
    if ([name, about].some((said) => NOTHING_SAID.test(said.trim()))) {
      throw new Error("Nothing was written down: ask the caller for what they have not said yet, their name or what the call is about.");
    }
    this.message = { name, about };
    this.stage = "done";
    return this.message;
  }

  /** The view: the one block of the prompt that changes between two turns, and the last one the model reads. */
  override render() {
    return (
      <>
        {this.stage === "ask" && (
          <p>
            A question the documents answer, answer. Otherwise take a message: ask only for what the caller has not said
            yet, their name or what the call is about, and call takeMessage the moment you have both. Greet nobody twice.
          </p>
        )}
        {this.message && (
          <p>
            The message is written down: {this.message.name}, about {this.message.about}. Tell the caller, in one
            sentence, that their message reached the team. Then answer anything else the documents answer; when the
            caller wants nothing more, say goodbye and hang up.
          </p>
        )}
      </>
    );
  }
}
