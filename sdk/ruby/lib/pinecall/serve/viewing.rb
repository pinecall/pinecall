# frozen_string_literal: true

module Pinecall
  module Serve
    # The one console verb an agent's own process answers: its class's panel, for a conversation.
    # Every other verb is the CLI's companion's. Word for word the TypeScript serve entry's answers.
    module Viewing
      ONLY_THE_VIEW = "this process answers only view.render: the console's other verbs are the CLI's"

      module_function

      # The class's panel for the conversation asked, or a refusal with its status.
      def answer(klass, slug, verb, asked)
        raise DevRefused.new(404, ONLY_THE_VIEW) unless verb == "view.render"

        who = a_conversation(slug, asked)
        raise DevRefused.new(404, "#{slug} declares no view: nothing in this directory draws a panel") if klass.declared_panel.nil?

        begin
          Panel.draw(klass, who)
        rescue StandardError => e
          # The pane says it, and the conversation's screen keeps working.
          raise DevRefused.new(502, "#{slug}'s view failed: #{e.message}")
        end
      end

      def a_conversation(slug, asked)
        raise DevRefused.new(422, "a panel is asked for with a JSON object") unless asked.is_a?(Hash)

        named = %i[contact call].to_h do |name|
          value = asked[name]
          raise DevRefused.new(422, "#{name} is a name, and it was missing") unless value.is_a?(String) && !value.empty?

          [name, value]
        end
        Panel::Who.new(agent: slug, **named)
      end
    end
  end
end
