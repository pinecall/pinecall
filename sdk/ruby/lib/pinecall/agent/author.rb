# frozen_string_literal: true

module Pinecall
  class Agent
    # Tracks who is writing state, so each write is attributed to its tool or hook.
    #
    # Uses fiber storage, not a module variable: concurrent calls must not see each other's author.
    # `Fiber[]` is inherited by child fibers and separate per thread.
    module Author
      KEY = :pinecall_author

      module_function

      # The current author, or nil.
      def current
        Fiber[KEY]
      end

      # Run the block with state writes attributed to `name`.
      def with(name)
        held = Fiber[KEY]
        Fiber[KEY] = name
        begin
          yield
        ensure
          Fiber[KEY] = held
        end
      end
    end
  end
end
