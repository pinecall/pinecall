# frozen_string_literal: true

module Pinecall
  # One named prompt block and its region (`static` or `dynamic`).
  Block = Data.define(:name, :region, :text)

  # One rendered prompt: blocks in send order, plus the history between the two regions.
  Blocks = Data.define(:blocks, :history) do
    def [](name) = blocks.find { |block| block.name == name.to_s }&.text

    # Blocks before the history; cached by the provider.
    def static = blocks.select { |block| block.region == "static" }

    # Blocks after the history; replaced every turn.
    def dynamic = blocks.select { |block| block.region == "dynamic" }

    # Non-empty static blocks joined into one text.
    def instructions = static.map(&:text).reject(&:empty?).join("\n\n")
  end

  # Renders the prompt as named blocks in two regions.
  #
  # Static blocks precede the history and are cached; the view follows it and changes every turn.
  # Do not reorder them: the region boundary is the cache boundary. Blocks hold only the
  # operator's text; lookup results go in the history as tool results.
  module Prompt
    # Blocks every agent has, in send order.
    FRAMEWORK = [
      { name: "identity", region: "static" }.freeze,
      { name: "knowledge", region: "static" }.freeze,
      { name: "tools", region: "static" }.freeze,
      { name: "view", region: "dynamic" }.freeze
    ].freeze

    module Declaring
      # Declare or read the template for the `view` block.
      #
      #     view                          # views/<slug>.erb next to this file (the default)
      #     view "views/reception.erb"    # relative to this file
      #     view template: <<~ERB         # inline
      #
      # The default lookup runs once and is memoized.
      def view(path = nil, template: nil)
        unless path.nil? && template.nil?
          @view = template ? View.inline(template, "#{name} (inline view)") : View.file(beside_this_file(path))
          return @view
        end
        return @view if defined?(@view)

        @view = view_of_this_class || (superclass.respond_to?(:view) ? superclass.view : nil)
      end

      def view_of_this_class
        here = source_file
        return nil if here.nil?

        path = View.beside(here, slug)
        File.exist?(path) ? View.file(path) : nil
      end

      # Relative paths resolve against the class's file, not the working directory.
      def beside_this_file(path)
        here = source_file
        return path if here.nil? || path.start_with?("/")

        File.expand_path(path, File.dirname(here))
      end

      def source_file
        found = name && Object.const_source_location(name)
        found&.first
      end
    end

    module_function

    def render(agent, resumed: false, remembered: [], line: nil)
      reading = reading_for(agent, resumed:, remembered:, line:)
      blocks = FRAMEWORK.map do |spec|
        Block.new(name: spec[:name], region: spec[:region], text: text_of(agent, spec[:name], reading))
      end
      Blocks.new(blocks:, history: history(agent))
    end

    # The class docstring, the framework's rules and protocols, and the channel's. Reads no state.
    def identity(agent)
      [agent.doc, tagged("rules", Rules::RULES), tagged("protocols", Rules::PROTOCOLS), channel(agent)]
        .compact.reject { |part| part.strip.empty? }.join("\n\n")
    end

    # Static because a call never changes its channel or medium. With no call (an offline prompt), a
    # phone call's.
    def channel(agent)
      return nil if agent.class.channel_rules == false

      call = agent.call? ? agent.call : nil
      tagged("channel", Rules.channel_rules_for(call&.channel || "phone", call&.medium || "voice"))
    end

    # Every declared tool's docstring, visible or not; schemas travel separately on the wire.
    def tools(agent)
      docs = agent.tools.map { |spec| "- #{spec[:name]}: #{spec[:description]}" }.join("\n")
      tagged("tools", docs)
    end

    # The runtime owns the turns; the framework adds only the summaries left by `collapse`.
    def history(agent)
      agent.changes.select { |change| change.field == "@summary" }
           .map { |change| "#{collapsed(change.seq)}\n#{change.next}" }
           .join("\n\n")
    end

    # Marker for a collapsed stretch of the call.
    def collapsed(seq) = "<!-- collapsed: #{JSON.generate({ seq: })} -->"

    def view(agent, reading)
      view = agent.class.view
      view.nil? ? "" : view.render(reading)
    end

    # The view's scope: state, call context, and remembered facts (queryable, never printed).
    def reading_for(agent, resumed: false, remembered: [], line: nil)
      Reading.new(agent.snapshot.merge(resumed:, call: line || { channel: "web" }), remembered)
    end

    # What `Pinecall::Serve`'s `prompt` prints: every block under its header.
    def header_for(section, region = nil) = "── #{[section, region && "(#{region})"].compact.join(" ")} ──"

    # The prompt as one page, as `pinecall prompt` prints it.
    def show(agent, **context)
      rendered = render(agent, **context)
      sections = rendered.static.map { |block| [header_for(block.name, block.region), block.text] }
      sections << [header_for("history"), rendered.history]
      sections += rendered.dynamic.map { |block| [header_for(block.name, block.region), block.text] }
      sections.map { |header, text| "#{header}\n#{text}".rstrip }.join("\n\n")
    end

    def text_of(agent, called, reading)
      case called
      when "identity" then identity(agent)
      # Filled by the gateway from the agent's settings (`pinecall agent knowledge edit`).
      when "knowledge" then ""
      when "tools" then tools(agent)
      when "view" then view(agent, reading)
      end
    end

    def tagged(name, body)
      body.to_s.empty? ? "" : "<#{name}>\n#{body}\n</#{name}>"
    end
  end
end
