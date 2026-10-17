# frozen_string_literal: true

# {{Title}}: the class is the agent — its state, its tools, and beside it in views/ its prompt.

require "pinecall"

# You answer the phone for the business. Short sentences: everything you say is read aloud.
# You answer what the business's documents say. For anything else you take a message: who is calling
# and what it is about. You never promise when they will hear back.
class {{Class}} < Pinecall::Agent
  # What a model in a hurry writes where the caller said nothing: never a message.
  NOTHING_SAID = %r{\A(n/?a|none|unknown|unspecified|not (specified|given|provided|said)|tbd|-)?\z}i

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
