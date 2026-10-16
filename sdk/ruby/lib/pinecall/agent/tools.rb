# frozen_string_literal: true

module Pinecall
  class Agent
    # One declared tool: its local options and the spec sent on the wire.
    Declaration = Data.define(:name, :options, :spec)

    # Tool declaration and visibility. `tool` marks the next method defined, like Sorbet's `sig`.
    module Tools
      module Declaring
        # Declare the next method as a tool.
        #
        #     # Reserva la hora que el paciente ya ha confirmado.
        #     tool stage: :book, confirm: "Le reservo el {{chosen}}. ¿Lo confirmo?"
        #     def book(chosen:)
        #
        # @param when [Proc] visibility predicate, evaluated against the state
        # @param stage [Symbol, Array<Symbol>] shorthand for a `when` on the stage field
        # @param confirm [String] read-back spoken before running; marks the tool irreversible
        # @param announce [String] what the agent says as the tool starts, when its turn said nothing
        # @param preview [Integer] rows of a list result the model sees
        # @param pii [Array<Symbol>] parameters with personal data, masked in the log
        # @param timeout [Numeric] seconds the platform waits for the method
        # @param params [Hash{Symbol=>Object}] parameter types, e.g. `{ day: String, how_many: Integer }`
        def tool(**options)
          unknown = options.keys - %i[when stage confirm announce preview pii timeout params doc]
          raise DeclarationRefused, "@tool takes no #{unknown.join(", ")}" unless unknown.empty?

          @pending_tool = options
        end

        # Attaches a pending `tool` declaration to the method just defined.
        def method_added(name)
          super
          options = @pending_tool
          return if options.nil?

          @pending_tool = nil
          declare_tool(name, options)
        end

        # Declared tools by name, including inherited ones.
        def declared_tools
          @declared_tools ||= superclass.respond_to?(:declared_tools) ? superclass.declared_tools.dup : {}
        end

        def tool_named(name) = declared_tools[name.to_sym]

        # Validate at load what the gateway would refuse later.
        def declare_tool(name, options)
          options = Spec.lower(self, name, options)
          spec = Spec.build(self, name, options)
          declared_tools[name.to_sym] = Declaration.new(name: name.to_sym, options:, spec:)
        end
      end

      # ── instance methods ─────────────────────────────────────────────────────

      # The class comment, sent as the top of the prompt.
      def doc = Doc.for_class(self.class)

      # Every declared tool spec, visible or not.
      def tools = self.class.declared_tools.values.map(&:spec)

      # Tool specs whose `when` holds for the current state.
      def visible_tools = visible_declarations.map(&:spec)

      def visible_declarations
        state = snapshot
        self.class.declared_tools.values.select { |declared| Tools.shows?(declared, state) }
      end

      # Run a tool as the bridge does, with its writes attributed to it.
      def run_tool(name, arguments = {})
        declared = self.class.tool_named(name)
        raise ToolFailed, "#{name}: this agent declares no such tool" if declared.nil?

        Tools.run(self, declared, arguments)
      end

      class << self
        # `stage:` was already lowered to a `when` at declaration.
        def shows?(declared, state)
          asked = declared.options[:when]
          asked.nil? || ask(asked, state)
        end

        # A `when` may take the state as an argument (`->(s) { s.slots.any? }`) or be evaluated
        # against it (`-> { slots.any? }`).
        def ask(asked, state)
          reading = state.is_a?(Reading) ? state : Reading.new(state)
          asked.arity.zero? ? reading.instance_exec(&asked) : asked.call(reading)
        end

        # Check arguments, run the method with its writes attributed, and trim to `preview`.
        def run(agent, declared, arguments)
          named = arguments.to_h { |key, value| [key.to_sym, value] }
          refuse_arguments_the_tool_never_asked_for(declared, named)
          result = Author.with(declared.name.to_s) { agent.public_send(declared.name, **named) }
          preview(result, declared.options[:preview])
        end

        # Trims only what the model sees; state keeps every row.
        def preview(result, rows)
          return result unless rows.is_a?(Integer) && result.is_a?(Array) && result.size > rows

          result.first(rows)
        end

        def refuse_arguments_the_tool_never_asked_for(declared, named)
          declared_names = (declared.spec[:parameters][:properties] || {}).keys
          unknown = named.keys - declared_names
          return if unknown.empty?

          raise ToolFailed, "#{declared.name}: it takes no #{unknown.join(", ")}"
        end
      end
    end
  end
end
