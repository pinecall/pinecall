# frozen_string_literal: true

# What a served process prints of its agent's entries: the values the agent declared private, masked as the call's log masks them.

module Pinecall
  module Serve
    # One agent's private names and, as its tool calls pass, the private values they carried.
    class Masking
      MASK = "***"

      # Shorter than this a value is never learned as a secret: "7", "ok" or "Al" cannot be told from a
      # word, and hunting it in what else is written would mask every such digit or word. The argument is
      # still masked by its name; only its value is not looked for.
      LEAST_SECRET_LENGTH = 3

      # What the agent wrote down, by entry: the fields of its data a private value may be in. What was
      # said is the caller's and the model's words, and never masked.
      WRITTEN_DOWN = {
        "tool.call" => %i[arguments],
        "tool.result" => %i[output error summary],
        "state.changed" => %i[state],
        "call.attached" => %i[state],
        "custom" => %i[data]
      }.freeze

      # `declared` is the agent's wire config: the arguments its tools list under `pii`, and the state
      # fields declared `pii`.
      def initialize(declared)
        @arguments = (declared[:tools] || []).to_h { |tool| [tool[:name].to_s, Array(tool[:pii]).map(&:to_sym)] }
        @fields = (declared[:state_fields] || []).filter_map { |field| field[:name].to_sym if field[:visibility].to_s == "pii" }
        @values = Set.new
        @pattern = nil
      end

      # The entry with every private value masked: by name where the agent named it, by value wherever
      # else it was written down. An entry with nothing private to hide is the entry itself.
      def entry(entry)
        fields = WRITTEN_DOWN[entry.type]
        return entry if fields.nil?

        named = @arguments.fetch(entry.data[:name].to_s, [])
        return entry unless @values.any? || @fields.any? || (entry.type == "tool.call" && named.any?)

        learn(named, entry.data) if entry.type == "tool.call"
        data = entry.data.dup
        fields.each { |field| data[field] = masked(data[field], names_in(entry, field, named)) if data.key?(field) }
        entry.with(data:)
      end

      private

      def names_in(entry, field, named)
        return named if entry.type == "tool.call" && field == :arguments

        field == :state ? @fields : []
      end

      def learn(named, data)
        given = data[:arguments]
        return unless given.is_a?(Hash)

        known = @values.size
        named.each { |name| @values.merge(leaves(given[name])) }
        @pattern = whole_words if @values.size != known
      end

      # A hash is masked member by member; any other value is masked of the secrets alone.
      def masked(value, names)
        return scrubbed(value) unless value.is_a?(Hash)

        value.to_h { |name, member| [name, names.include?(name.to_sym) ? MASK : scrubbed(member)] }
      end

      # A leaf that is a private value goes whole; a string that holds one as a whole word has it
      # replaced, so the rest of what it said stays readable.
      def scrubbed(value)
        return value if @pattern.nil?

        case value
        when String then value.gsub(@pattern, MASK)
        when Numeric then @values.include?(value.to_s) ? MASK : value
        when Array then value.map { |item| scrubbed(item) }
        when Hash then value.to_h { |name, member| [name, scrubbed(member)] }
        else value
        end
      end

      # A value is a secret where it stands as a whole word: `Ana` is no part of `Banana` or `Anabel`, nor
      # `7` of `1700`. The longest comes first, so a value that holds another is masked whole.
      def whole_words
        ordered = @values.sort_by { |secret| -secret.length }
        Regexp.new("(?<![[:alnum:]_])(?:#{ordered.map { |secret| Regexp.escape(secret) }.join("|")})(?![[:alnum:]_])")
      end

      # Every string and number inside a value, as text; a blank is no secret, it would mask everything.
      def leaves(value)
        case value
        when String then secret_of(value.strip)
        when Numeric then secret_of(value.to_s)
        when Array then value.flat_map { |item| leaves(item) }
        when Hash then value.values.flat_map { |member| leaves(member) }
        else []
        end
      end

      def secret_of(text) = text.length >= LEAST_SECRET_LENGTH ? [text] : []
    end
  end
end
