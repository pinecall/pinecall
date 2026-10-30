# frozen_string_literal: true

# {{Title}}: the class is the agent — its state, its tools, and beside it in views/ its prompt.

require "pinecall"

# You answer the phone for the business. Short sentences: everything you say is read aloud.
# You answer what the business's documents say. For anything else you take a message: who is calling
# and what it is about. You never promise when they will hear back.
class {{Class}} < Pinecall::Agent
  # What a model in a hurry writes where the caller said nothing: never a message.
  NOTHING_SAID = %r{\A(n/?a|none|unknown|unspecified|not (specified|given|provided|said)|tbd|-)?\z}i

  # The eight judges Pinecall recommends, on for every call; the agent's own are the files under judges/.
  judges on: %w[consent grounded promises disclosed identified honoured-stop ended-well expected-outcome]
  # Pinecall's callers this agent is tested with, and its own under test/personas/.
  personas on: %w[in-a-hurry wrong-number]

  stage :ask, :done

  state :message

  # Writes down the caller's message. Call it as soon as the caller has said their name and what the call is
  # about, in that same turn and without reading it back first; never with a blank or a guess.
  tool stage: :ask, pii: %i[name]
  def take_message(name:, about:)
    raise ArgumentError, "Nothing was written down: ask the caller for what they have not said yet, their name or what the call is about." if [name, about].any? { |said| NOTHING_SAID.match?(said.to_s.strip) }

    self.message = { name:, about: }
    self.stage = :done
    message
  end
end
