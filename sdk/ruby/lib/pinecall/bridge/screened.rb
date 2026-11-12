# frozen_string_literal: true

module Pinecall
  module Bridge
    # A call's screen as the bridge keeps it: drawn from the agent, sent in the state when it moved,
    # and moved by the conversation's turns.
    module Screened
      # The screen a call's page was last sent, and whether this turn kept its scene.
      class Kept
        attr_accessor :screen, :key, :by_user, :kept

        def initialize
          @screen = nil
          @key = "[]"
          @by_user = false
          @kept = false
        end
      end

      module_function

      # Whether one of the classes draws a screen: its field is then public.
      def screens?(classes) = classes.any? { |klass| Screen.draws?(klass) }

      # A class with a screen declares its field public, and with tasks the page's event.
      def declared(options, tasks:)
        fields = [*options[:state_fields], { name: Screen::SCREEN, visibility: "public" }]
        events = tasks ? [*options[:events], { name: Screen::TASK_GIVE, from: ["participant"] }] : options[:events]
        options.merge(state_fields: fields, events:).compact
      end

      # Draw the screen with what is shown over it; true when it is not the one already sent.
      def redrawn(drawn, shown, kept)
        screen = Screen.screen_of([drawn, shown])
        key = JSON.generate(screen)
        return false if key == kept.key

        kept.screen = screen
        kept.key = key
        true
      end

      # The call's state as the gateway is told it: the agent's own, and its screen once drawn.
      def state_with(snapshot, kept) = kept.screen.nil? ? snapshot : snapshot.merge(Screen::SCREEN.to_sym => kept.screen)

      # A state the gateway kept, without the screen: it is drawn again, never restored.
      def unscreened(state) = state.reject { |name, _| name.to_s == Screen::SCREEN }

      # The tool the classes of a call move their screen with, declared once for all of them.
      def scene_tools(classes, taken)
        scenes = classes.each_with_object({}) { |klass, all| all.merge!(Screen.scenes_of(klass)) }
        return [] if scenes.empty?
        if taken.include?(Screen::SHOW_SCREEN)
          raise DeclarationRefused, "#{Screen::SHOW_SCREEN} is the tool a screen is moved with, and an agent declares a tool so named"
        end

        [Screen.showing_tool(scenes)]
      end

      # The tool the class serving the call moves its screen with, when it declares scenes.
      def scene_tool_of(klass)
        scenes = klass.declared_scenes
        scenes.empty? ? [] : [Screen.showing_tool(scenes)]
      end

      # The model chose a scene, or none: it is the call's now, and kept through this turn.
      def scene_chosen(world, kept, klass, scene)
        scene = scene.to_s
        scenes = klass.declared_scenes
        return "There is no scene #{scene}: #{[*scenes.keys, Screen::NO_SCENE].join(", ")}." unless scene == Screen::NO_SCENE || scenes.key?(scene)

        world.scene = scene == Screen::NO_SCENE ? nil : scene
        kept.kept = true
        "shown"
      end

      # A turn went by; one the caller opened that kept no scene takes it away once the agent waits.
      # True when the scene moved.
      def turned(type, world, kept)
        if type == "turn.user"
          kept.by_user = true
          kept.kept = false
          return false
        end
        return false unless type == "agent.waiting" && kept.by_user

        kept.by_user = false
        return false if kept.kept || world.scene.nil?

        world.scene = nil
        true
      end
    end
  end
end
