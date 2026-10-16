# frozen_string_literal: true

module Pinecall
  class Agent
    # Class-level configuration (state lives on the instance).
    #
    # A class declares its contract: tools, state, view. It may also declare its environment —
    # voice, models, language, greeting, memory, knowledge — and whatever it declares wins over the
    # agent's settings for that field.
    module Config
      # `phone`, `whatsapp` and `web` are accepted for compatibility but ignored. `channel_rules
      # false` leaves the `<channel>` block out of the prompt.
      AS_WRITTEN = %i[phone whatsapp web channel_rules].freeze

      # The settings a class may declare. Must match the TypeScript package's `ENVIRONMENT`.
      ENVIRONMENT = %i[language voice llm stt judge greeting hangup turn says hears knowledge docs memory record].freeze

      # The ones written as the wire's own fields, keyword by keyword: `greeting say: "…"`.
      AS_KEYWORDS = %i[turn knowledge docs memory].freeze

      NO_VOICE = "a voice the class declares names its vendor and the voice: voice \"<vendor>\", \"<voice id>\""

      NO_OPENING = "a greeting is the words, as a string, or :improvise for the model's own: improvise(\"…\") gives it an instruction"
      NO_ENDING = "hangup is when the model may end the call, in your words, or true whenever it judges the call done"

      # The model opens the call: on its prompt alone (an empty instruction), or with this one.
      Improvised = Data.define(:instruction, :interruptible)

      NOTHING = Object.new.freeze

      # An opening as the wire says it: words to `say`, or a `reply` the model opens on.
      def self.greeting_of(opening, interruptible)
        said = case opening
               when :improvise then { reply: "" }
               when Improvised then { reply: opening.instruction }
               when String then { say: opening }
               else raise DeclarationRefused, NO_OPENING
               end
        given = opening.is_a?(Improvised) ? opening.interruptible : interruptible
        given.nil? ? said : { **said, allow_interruptions: given }
      end

      # When the model may end the call: an empty `when` is whenever it judges.
      def self.hangup_of(ending)
        return { when: "" } if ending == true
        raise DeclarationRefused, NO_ENDING unless ending.is_a?(String) && !ending.strip.empty?

        { when: ending }
      end

      # `vendor/model`, or a vendor alone; the model id keeps every slash after the vendor's.
      def self.model_of(named)
        provider, _slash, model = named.to_s.partition("/")
        { provider:, model: }
      end

      module Declaring
        # Called with no argument, each reads the (possibly inherited) value.
        AS_WRITTEN.each do |field|
          define_method(field) do |value = NOTHING|
            return config[field] if value.equal?(NOTHING)

            config[field] = value
          end
        end

        # The voice, by its vendor and the vendor's own id for it. Declared, it wins over the
        # agent's settings; `builds` and `options` reach the vendor's plugin.
        def voice(provider = NOTHING, voice_id = nil, model: nil, builds: nil, options: nil)
          return environment[:voice] if provider.equal?(NOTHING)
          raise DeclarationRefused, NO_VOICE if voice_id.nil?

          environment[:voice] = { provider:, voice_id:, model:, builds:, options: }.compact
        end

        # The model that answers, `vendor/model` or a vendor alone:
        # `llm "openai/gpt-5.4-mini", builds: "responses.LLM", options: { use_websocket: true }`.
        def llm(model = NOTHING, temperature: nil, builds: nil, options: nil)
          return environment[:llm] if model.equal?(NOTHING)

          environment[:llm] = { **Config.model_of(model), temperature:, builds:, options: }.compact
        end

        # The ears, `vendor/model` or a vendor alone, and who says the caller's turn is over:
        # `end_of_turn: "stt"` the ears themselves (Deepgram Flux), `"livekit"` or `"smart-turn"`.
        def stt(model = NOTHING, builds: nil, options: nil, end_of_turn: nil)
          return environment[:stt] if model.equal?(NOTHING)

          ends = end_of_turn&.to_s&.tr("_", "-")
          environment[:stt] = { **Config.model_of(model), builds:, options:, end_of_turn: ends }.compact
        end

        # The model the agent's calls are judged on, over the org's choice and the platform's:
        # `judge "openai/qwen3-32b", options: { base_url: "http://gpu:8000/v1" }`. On a key of the
        # org's own, a local model's server among them, its evals are never billed; `builds` and
        # `options` run on the org's own key alone.
        def judge(model = NOTHING, builds: nil, options: nil)
          return environment[:judge] if model.equal?(NOTHING)

          environment[:judge] = { **Config.model_of(model), builds:, options: }.compact
        end

        # How a call opens: the words, said as written, or :improvise for the model's own. The
        # caller cannot cut it short unless `interruptible: true`.
        def greeting(opening = NOTHING, interruptible: nil)
          return environment[:greeting] if opening.equal?(NOTHING)

          environment[:greeting] = Config.greeting_of(opening, interruptible)
        end

        # The model opens the call with this instruction: `greeting improvise("…")`.
        def improvise(instruction = "", interruptible: nil) = Improvised.new(instruction, interruptible)

        # When the model may end the call: in your words, or `true` whenever it judges it done.
        def hangup(ending = NOTHING)
          return environment[:hangup] if ending.equal?(NOTHING)

          environment[:hangup] = Config.hangup_of(ending)
        end

        # `language "es"`, `says [{ word: "GSA", spoken: "ge ese a" }]`, `record false`.
        %i[language says record].each do |field|
          define_method(field) do |value = NOTHING|
            return environment[field] if value.equal?(NOTHING)

            environment[field] = value
          end
        end

        # The words the ears must know: `hears "Vidal", "Sanitas"`.
        def hears(*words)
          return environment[:hears] if words.empty?

          environment[:hears] = words.flatten
        end

        # `turn endpointing_ms: 300`, `docs base: "…", k: 4`, `memory remember: […], forget: […]`,
        # `knowledge path: "…", text: "…"`.
        AS_KEYWORDS.each do |field|
          define_method(field) do |**given|
            return environment[field] if given.empty?

            environment[field] = given
          end
        end

        # What the class declares of its environment, including inherited values.
        def environment
          @environment ||= superclass.respond_to?(:environment) ? superclass.environment.dup : {}
        end

        # Set the class docstring explicitly, for classes with no source file.
        def doc(text = NOTHING)
          return Doc.for_class(self) if text.equal?(NOTHING)

          @pinecall_doc = text
        end

        # Accept an external event from `:app` (the application's backend) or `:participant`
        # (a browser). Undeclared events never reach `on_event`.
        def accepts(name, from:)
          declared_events[name.to_s] = Array(from).map(&:to_s)
        end

        def declared_events
          @declared_events ||= superclass.respond_to?(:declared_events) ? superclass.declared_events.dup : {}
        end

        # Declared config, including inherited values.
        def config
          @config ||= superclass.respond_to?(:config) ? superclass.config.dup : {}
        end

        # The slug the class names itself, or nil when it names none.
        def declared_slug = @slug

        # Registration slug; defaults to the class name in kebab-case.
        def slug(name = NOTHING)
          return (@slug || default_slug) if name.equal?(NOTHING)

          @slug = name
        end

        # The AgentConfig sent to the gateway: the contract, and the environment the class declares.
        def wire_config(tools: nil)
          {
            **environment,
            prompt: Prompt::FRAMEWORK,
            tools:,
            state_fields: state_field_specs,
            events: event_specs,
            # Only the name: the panel is drawn on demand, by `view.render`.
            view: (declared_panel && { name: declared_panel.name }),
            uses_knowledge: (true if Searching.searches?(self))
          }.compact
        end

        def state_field_specs
          declared = state_visibility
          return nil if declared.empty?

          declared.map { |name, visibility| { name: name.to_s, visibility: visibility.to_s } }
        end

        def event_specs
          return nil if declared_events.empty?

          declared_events.map { |name, from| { name:, from: } }
        end

        private

        def default_slug
          (name || "agent").split("::").last
                           .gsub(/([a-z0-9])([A-Z])/, '\1-\2')
                           .gsub(/([A-Z]+)([A-Z][a-z])/, '\1-\2')
                           .downcase
        end
      end
    end
  end
end
