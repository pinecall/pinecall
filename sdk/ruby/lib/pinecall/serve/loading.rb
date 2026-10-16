# frozen_string_literal: true

# What the serve entry is told and loads: its flags, the class in a file, and a state field by field.

module Pinecall
  module Serve
    # Thrown when what was asked cannot be served at all; the entry exits 2 with its sentence.
    class CannotServe < Error; end

    # One agent file and the slug it is served as.
    Served = Data.define(:file, :slug)

    # The flags of one verb, as the CLI passes them.
    Flags = Data.define(:served, :console, :events, :prod, :state, :channel, :medium, :show_machine)

    module Loading
      module_function

      # `--file` and `--slug` paired by place; the rest by name. A flag nobody declared is refused.
      def parse(argv)
        found = { files: [], slugs: [], console: false, events: false, prod: false, state: {}, channel: "phone", medium: nil,
                  show_machine: false }
        words = argv.dup
        until words.empty?
          word = words.shift
          case word
          when "--file" then found[:files] << value_of(word, words)
          when "--slug" then found[:slugs] << value_of(word, words)
          when "--state" then found[:state].merge!(as_state(value_of(word, words)))
          when "--channel" then found[:channel] = value_of(word, words)
          when "--console", "--events", "--prod" then found[word.delete_prefix("--").to_sym] = true
          when "--show-machine" then found[:show_machine] = true
          when "--medium" then found[:medium] = value_of(word, words)
          else raise CannotServe, "serve has no flag #{word}"
          end
        end
        flags(found)
      end

      # `field=json`: the value is the field's, as JSON; a value that is not JSON is refused by its field.
      def as_state(pair)
        field, equals, value = pair.to_s.partition("=")
        raise CannotServe, "--state #{pair}: a field, =, and its value as JSON" if field.empty? || equals.empty?

        { field.to_sym => JSON.parse(value, symbolize_names: true) }
      rescue JSON::ParserError
        raise CannotServe, "--state #{field}: its value is not JSON"
      end

      # The class the file defines, refused when its own `slug` says another than the one it is served as.
      def load_served(served)
        klass = load_agent(served.file)
        declared = klass.declared_slug
        if !declared.nil? && declared.to_s != served.slug
          raise CannotServe, "#{served.file} says its slug is #{declared}, and it is served as #{served.slug}: the slug is its folder's name"
        end

        klass
      end

      # The last `Pinecall::Agent` the file defines.
      def load_agent(file)
        path = File.expand_path(file)
        raise CannotServe, "no agent at #{path}" unless File.exist?(path)

        before = Agent.written.dup
        begin
          loaded = require path
        rescue ScriptError, LoadError => e
          raise CannotServe, "#{path} did not load: #{e.message}"
        end
        # `require` answers false for a file already loaded: its class is found by its source.
        written = loaded ? Agent.written - before : Agent.written.select { |klass| klass.source_file == path }
        written = written.select(&:name)
        raise CannotServe, "#{path} declares no Pinecall::Agent" if written.empty?

        written.last
      end

      def value_of(flag, words)
        value = words.shift
        raise CannotServe, "#{flag} takes a value" if value.nil? || value.start_with?("--")

        value
      end

      def flags(found)
        files, slugs = found.values_at(:files, :slugs)
        if files.empty? || files.length != slugs.length
          raise CannotServe, "serve takes one --slug for each --file, and at least one of each"
        end
        unless Wire::Enums::CHANNEL.include?(found[:channel]) && [nil, *Wire::Enums::MEDIUM].include?(found[:medium])
          raise CannotServe, "--channel is phone, web or whatsapp, and --medium is voice or text"
        end

        Flags.new(served: files.zip(slugs).map { |file, slug| Served.new(file:, slug:) },
                  console: found[:console], events: found[:events], prod: found[:prod], state: found[:state],
                  channel: found[:channel], medium: found[:medium], show_machine: found[:show_machine])
      end
    end
  end
end
