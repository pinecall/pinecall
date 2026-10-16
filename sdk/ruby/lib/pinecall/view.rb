# frozen_string_literal: true

require "erb"

module Pinecall
  # An ERB template for the dynamic region of the prompt, rendered with the state in scope.
  #
  #     <% if stage == :identify -%>
  #     Saluda y pide nombre y teléfono.
  #     <% end -%>
  #
  # The view carries the operator's authority, so never splice external content (memory,
  # knowledge results) into it; that reaches the model as tool results in the history.
  #
  # In scope: every state field by name, `resumed`, `call[:channel]`, `call[:claimed]` (the page
  # code this call claimed, or nil), `remembers?(text)`.
  class View
    # Default location: `views/<slug>.erb` next to the class's file.
    def self.beside(file, slug) = File.join(File.dirname(file), "views", "#{slug}.erb")

    # Load a template file; the path is kept so errors report the template line.
    def self.file(path)
      raise Error, "there is no view at #{path}" unless File.exist?(path)

      new(File.read(path), path)
    end

    def self.inline(template, called = "(inline view)") = new(template, called)

    attr_reader :path

    def initialize(template, path)
      @path = path
      @erb = ERB.new(template, trim_mode: "-")
      @erb.filename = path
    end

    def render(reading) = tidy(@erb.result(Context.new(reading).binding_for_the_template))

    # Strip trailing spaces, collapse blank-line runs, trim both ends.
    def tidy(text)
      text.lines.map { |line| line.rstrip + "\n" }.join.gsub(/\n{3,}/, "\n\n").strip
    end

    # Template scope: state fields by name plus a few helpers; unknown names raise.
    class Context
      def initialize(reading)
        @reading = reading
      end

      def binding_for_the_template = binding

      # Join items one per line.
      def each_line(items) = Array(items).map { |item| item.to_s.strip }.join("\n")

      # The whole reading, to pass on.
      def state = @reading

      def respond_to_missing?(name, include_private = false)
        @reading.respond_to?(name) || super
      end

      def method_missing(name, *args, &block)
        return @reading.public_send(name, *args, &block) if @reading.respond_to?(name)

        super
      end
    end
  end
end
