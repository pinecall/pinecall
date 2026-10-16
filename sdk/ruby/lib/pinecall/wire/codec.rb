# frozen_string_literal: true

# Entries and commands read and written: a log line decoded, a command built and encoded.

module Pinecall
  module Wire
    # One log line. The streamed and stored forms are identical, and `seq` is assigned before the
    # write returns, so two readers never disagree.
    Entry = Data.define(:seq, :ts, :call, :agent, :type, :ephemeral, :data)

    # One app-to-gateway instruction. The gateway answers with the events it produces, or with an
    # `error` naming the command's id.
    Command = Data.define(:type, :agent, :call, :id, :data)

    # An entry read as what it means: the wire type, and the payload that type names.
    Event = Data.define(:type, :data)

    # JSON encoding and decoding. Keys are symbols in Ruby and strings on the wire; both are
    # snake_case, so unlike TypeScript there is no key renaming.
    module Codec
      module_function

      # One log line from parsed JSON. A shape the protocol does not declare is a WireError.
      def decode_entry(raw)
        fields = symbolize(raw)
        Validate.call!("Entry", fields, where: "entry")
        Entry.new(**fields)
      end

      # The entry's data as the shape its type names. An unknown type is a WireError.
      def event_of(entry)
        shape = Registry::EVENTS[entry.type]
        raise WireError, "unknown event type: #{entry.type}" if shape.nil?

        Validate.call!(shape, entry.data, where: entry.type)
        Event.new(type: entry.type, data: entry.data)
      end

      # Build a command frame, validating its data and then the whole envelope. Validating here
      # keeps the backtrace in the app's code.
      def command(type:, agent:, data:, call: nil, id: nil)
        shape = Registry::COMMANDS[type]
        raise WireError, "unknown command type: #{type}" if shape.nil?

        Validate.call!(shape, data, where: type)
        frame = { type:, agent:, call:, data: }
        frame[:id] = id unless id.nil?
        Validate.call!("Command", frame, where: type)
        Command.new(type:, agent:, call:, id:, data:)
      end

      # A frame as JSON text. A command without an id omits the key (the schema refuses null);
      # `call` stays null, since a command about the agent itself belongs to no call.
      def encode(frame)
        fields = frame.to_h
        fields.delete(:id) if frame.is_a?(Command) && fields[:id].nil?
        JSON.generate(fields)
      end

      # Whether an entry of this type is one a store may drop and a slow reader may miss.
      def ephemeral?(type)
        Registry::EPHEMERAL_EVENTS.include?(type)
      end

      # JSON.parse can symbolize keys, but a hand-built Hash may use strings.
      def symbolize(value)
        case value
        when Hash then value.to_h { |key, inner| [key.to_sym, symbolize(inner)] }
        when Array then value.map { |inner| symbolize(inner) }
        else value
        end
      end
    end
  end
end
