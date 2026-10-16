# frozen_string_literal: true

require "ripper"

# Whether a class searches its knowledge bases, read off its own source with Ripper's tokens.

module Pinecall
  class Agent
    # A token walk, not a regex: `knowledge.search` inside a string or a comment is one token of
    # another kind, and does not count. Any method of the file counts, not only tools.
    module Searching
      SEARCHES = [%w[knowledge . search], %w[call . search]].freeze

      module_function

      # Whether the class's file calls `knowledge.search` or `call.search`. Sent at registration as
      # `uses_knowledge`, so a world with no base attached is refused when the agent registers.
      def searches?(klass)
        file = Object.const_source_location(klass.name.to_s)&.first
        return false if file.nil? || !File.exist?(file)

        in_source?(File.read(file))
      end

      def in_source?(source)
        words = Ripper.lex(source).filter_map do |(_, kind, token)|
          token if %i[on_ident on_period on_op].include?(kind) || (kind == :on_kw && token == "self")
        end
        words.each_cons(3).any? { |three| SEARCHES.include?(three) }
      end
    end
  end
end
