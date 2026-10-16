// {{Title}}: the class is the agent — its state, its tools, and render(), its prompt.

import { Agent, tool, type Stages } from "@pinecall/agents";

/**
 * You answer the phone for the business. Short sentences: everything you say is read aloud.
 * You answer what the business's documents say. For anything else you take a message: who is calling
 * and what it is about. You never promise when they will hear back.
 */
export default class {{Class}} extends Agent {
  stage: Stages<"ask" | "done"> = "ask";
  message?: { name: string; about: string } | undefined;

  /**
   * Writes down the caller's message. Call it as soon as the caller has said their name and what the call is
   * about, in that same turn and without reading it back first; never with a blank or a guess.
   */
  @tool({ stage: "ask", pii: ["name"] })
  async takeMessage(name: string, about: string): Promise<{ name: string; about: string }> {
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
            Greet the caller. A question the documents answer, answer; otherwise ask for their name and what the call is
            about.
          </p>
        )}
        {this.message && (
          <p>
            The message is written down: {this.message.name}, about {this.message.about}. Tell them it reached the
            team, say goodbye and hang up.
          </p>
        )}
      </>
    );
  }
}
