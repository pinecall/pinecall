# frozen_string_literal: true

# {{Title}}: the class is the agent — its state, its tools, and beside it in views/ its prompt.

require "pinecall"

# You answer the phone for the business. Short sentences: everything you say is read aloud.
# You answer what the business's documents say. For anything else you take a message: who is calling
# and what it is about. You never promise when they will hear back.
class {{Class}} < Pinecall::Agent
  stage :ask, :done

  state :message

  # Writes down the caller's message. Call it as soon as the caller has said their name and what the call is
  # about, in that same turn and without reading it back first; never with a blank or a guess.
  tool stage: :ask, pii: %i[name]
  def take_message(name:, about:)
    self.message = { name:, about: }
    self.stage = :done
    message
  end
end
