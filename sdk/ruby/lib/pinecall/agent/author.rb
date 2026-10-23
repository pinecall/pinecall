# frozen_string_literal: true

module Pinecall
  class Agent
    # Tracks who is writing state, so each write is attributed to its tool or hook.
    #
    # Uses fiber storage, not a module variable: concurrent calls must not see each other's author.
    # `Fiber[]` is inherited by child fibers and separate per thread.
    module Author
      KEY = :pinecall_author
      CALL = :pinecall_author_call

      module_function

      # The current author, or nil.
      def current
        Fiber[KEY]
      end

      # The model's id for the tool call the current author is running, or nil.
      def call_id
        Fiber[CALL]
      end

      # Run the block with state writes attributed to `name`; a tool also says the model's `call_id`.
      def with(name, call_id = nil)
        held = [Fiber[KEY], Fiber[CALL]]
        Fiber[KEY] = name
        Fiber[CALL] = call_id
        begin
          yield
        ensure
          Fiber[KEY], Fiber[CALL] = held
        end
      end
    end
  end
end
