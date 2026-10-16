# frozen_string_literal: true

module Pinecall
  # The console panel an agent draws beside a conversation: the TypeScript package's `@view` and
  # its `@pinecall/agents/panels` tags. The nodes are the same JSON, drawn by the console's own
  # components, so a tenant's panel cannot inject styles or scripts.
  #
  #     panel "Ficha" do |who|
  #       patient = Crm.find(who.contact)
  #       panel patient.name do
  #         rows do
  #           row "Alta", patient.since
  #           row "Zona", patient.area
  #         end
  #         badge "con saldo", tone: :warn if patient.owes?
  #       end
  #     end
  #
  # A panel identifies a thread, not live call state: it is drawn for ended calls too, so it fetches
  # its data from the tenant's own systems.
  module Panel
    # The conversation a panel is drawn for: the agent, the other party, the thread's newest call.
    Who = Data.define(:agent, :contact, :call)

    # A class's declared panel: its title and the block that draws it.
    Declared = Data.define(:name, :draw)

    TONES = %w[neutral good warn bad].freeze

    # A value as the console shows it: nil and booleans are "", a whole float is written whole.
    def self.said(value)
      case value
      when nil, true, false then ""
      when Float then value.finite? && (value % 1).zero? ? value.to_i.to_s : value.to_s
      else value.to_s
      end
    end

    # Draw a class's panel for one conversation: `{ name:, nodes: }`, what `view.render` answers.
    def self.draw(klass, who)
      declared = klass.declared_panel
      drawing = Drawing.new(klass)
      drawing.instance_exec(who, &declared.draw)
      { name: declared.name, nodes: drawing.nodes }
    end

    module Declaring
      # Declare the class's console panel; the block draws it for a `Who`. One per class, and a
      # subclass does not inherit it.
      def panel(name = "View", &draw)
        raise DeclarationRefused, "panel takes the block that draws it" if draw.nil?

        standing = @pinecall_panel
        unless standing.nil?
          raise DeclarationRefused,
                "#{self.name || "this class"} declares two panels (#{standing.name} and #{name}); a class draws one panel"
        end

        @pinecall_panel = Declared.new(name: name.to_s, draw:)
      end

      # The panel this class declares itself, or nil.
      def declared_panel = @pinecall_panel
    end

    # What a panel's block draws on: one method per node of the console's closed catalogue. Any
    # other method the block calls is the agent class's, where a tenant keeps its own helpers.
    class Drawing
      attr_reader :nodes

      def initialize(klass)
        @klass = klass
        @nodes = []
      end

      # A titled section; several stack vertically.
      def panel(title = nil, &) = add(tag: "panel", title: title.nil? ? nil : Panel.said(title), children: inside(&))

      # A list of labelled rows.
      def rows(&) = add(tag: "rows", children: inside(&))

      # A labelled line: `row "Alta", "12 Mar 2024"`.
      def row(label, value = nil) = add(tag: "row", label: Panel.said(label), value: Panel.said(value))

      # A prominent labelled number.
      def stat(label, value) = add(tag: "stat", label: Panel.said(label), value: Panel.said(value))

      # A table. Each row is an array in column order, or a hash keyed by the columns' names.
      def table(columns:, rows:)
        add(tag: "table", columns: columns.map { |column| Panel.said(column) }, rows: rows.map { |row| cells(row, columns) })
      end

      # A status badge with a tone: neutral, good, warn or bad; a word it does not know is neutral.
      def badge(text, tone: :neutral)
        add(tag: "badge", tone: TONES.include?(tone.to_s) ? tone.to_s : "neutral", text: Panel.said(text))
      end

      # A line of text; an empty one draws nothing.
      def text(said)
        line = Panel.said(said).strip
        line.empty? ? nil : add(tag: "text", text: line)
      end

      def respond_to_missing?(name, include_private = false) = @klass.respond_to?(name) || super

      def method_missing(name, ...)
        return super unless @klass.respond_to?(name)

        @klass.public_send(name, ...)
      end

      private

      def add(node)
        @nodes << node
        nil
      end

      # The nodes a nested block draws, collected apart from the ones around it.
      def inside
        outer = @nodes
        @nodes = []
        yield if block_given?
        @nodes
      ensure
        @nodes = outer
      end

      def cells(row, columns)
        case row
        when Array then row.map { |cell| Panel.said(cell) }
        when Hash then columns.map { |column| Panel.said(row.fetch(column) { row[column.to_s] || row[column.to_s.to_sym] }) }
        else [Panel.said(row)]
        end
      end
    end
  end
end
