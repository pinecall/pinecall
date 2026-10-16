# frozen_string_literal: true

# The runtime's wire as this gem speaks it: the shapes, a validator, the codec and the reducer.

require "json"
require "set"

require_relative "wire/errors"
require_relative "wire/enums"
require_relative "wire/shapes"
require_relative "wire/registry"
require_relative "wire/validate"
require_relative "wire/codec"
require_relative "wire/state"
require_relative "wire/reduce"

module Pinecall
  # The wire between gateway and app: events the gateway writes, commands the app sends.
  module Wire
    class << self
      # One log line from parsed JSON.
      def decode_entry(raw) = Codec.decode_entry(raw)

      # The entry's data as the shape its type names.
      def event_of(entry) = Codec.event_of(entry)

      # One command frame, checked against the shape its type names.
      def command(...) = Codec.command(...)

      # A frame as JSON text.
      def encode(frame) = Codec.encode(frame)

      # Fold a log into the state it means.
      def reduce(entries) = Reduce.reduce(entries)

      # One entry folded into a state, for a reader following a log as it happens.
      def apply(state, entry) = Reduce.apply(state, entry)

      # The state of an empty log.
      def initial_state = State.initial
    end
  end
end
