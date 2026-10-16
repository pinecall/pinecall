# frozen_string_literal: true

module Pinecall
  # Read-only view of a state snapshot for `when:` and views: `s.slots` and `s[:slots]` are
  # equivalent, and an undeclared field raises instead of returning nil.
  class Reading
    # @param remembered [Array<String>] facts known about the caller, supplied by the runtime
    def initialize(state, remembered = [])
      @state = state
      @remembered = remembered
    end

    def to_h = @state

    def [](name) = @state[name.to_sym]

    def key?(name) = @state.key?(name.to_sym)

    def fetch(name, *rest) = @state.fetch(name.to_sym, *rest)

    # Whether a remembered fact contains `text`. Views may branch on facts but never print them;
    # facts reach the model only as tool results.
    def remembers?(text) = @remembered.any? { |fact| fact.to_s.include?(text.to_s) }

    def respond_to_missing?(name, include_private = false)
      @state.key?(name) || super
    end

    def method_missing(name, *args)
      return @state[name] if args.empty? && @state.key?(name)

      super
    end

    def inspect = "#<Pinecall::Reading #{@state.inspect}>"
  end
end
