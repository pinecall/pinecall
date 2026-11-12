# frozen_string_literal: true

module Pinecall
  # A screen: what an agent puts on its caller's page, as named parts the page draws its own way.
  module Screen
    # The field of a call's state its screen travels in, public to the caller's own page.
    SCREEN = "screen"
    # The event a page answers a task with: `{ task: "phone", given: { number: "…" } }`.
    TASK_GIVE = "task.give"
    # The tool the model moves the caller's screen with, offered to a class that declares scenes.
    SHOW_SCREEN = "show_screen"
    # The scene that takes what a tool put up away: the screen with nothing chosen.
    NO_SCENE = "none"

    A_PART = /\A[a-z][a-z0-9-]*\z/
    A_SCENE = /\A[a-z][a-z0-9_-]*\z/

    # One part with what it was given and what it holds, as `screen` returns it.
    Shown = Data.define(:part, :props, :children)

    # A part of the agent's own: `Agenda = Pinecall.part("agenda")`, drawn as `Agenda.(slots:)`.
    Part = Data.define(:name) do
      # This part with these props, holding these children.
      def call(*children, **props) = Shown.new(part: name, props:, children:)
    end

    module_function

    # Declare a part; the name is what the page maps to a component of its own.
    def part(name)
      name = name.to_s
      unless A_PART.match?(name)
        raise DeclarationRefused, "a part's name is lowercase letters, digits and dashes, and \"#{name}\" is not: it is what the page maps to its component"
      end

      Part.new(name:)
    end

    # What `screen` returned, as the parts a page reads: parts, words, and arrays of them.
    def screen_of(drawn)
      case drawn
      when nil, true, false then []
      when String then drawn.strip.empty? ? [] : [drawn.strip]
      when Numeric then [drawn.to_s]
      when Shown then [{ part: drawn.part, props: Wire::Codec.plain(drawn.props) || {}, children: screen_of(drawn.children) }]
      when Array then drawn.flat_map { |one| screen_of(one) }
      else raise DeclarationRefused, "a screen is parts, words and arrays of them, and #{drawn.class} is none"
      end
    end

    # Whether the class draws a screen of its own.
    def draws?(klass) = klass.instance_method(:screen).owner != Agent

    # The scenes a class declares, each with what it shows; checked against its tools' `shows`.
    def scenes_of(klass)
      scenes = klass.declared_scenes
      klass.declared_tools.each_value do |declared|
        shows = declared.options[:shows]
        next if shows.nil? || scenes.key?(shows.to_s)

        raise DeclarationRefused, "#{klass}.#{declared.name} shows #{shows}, which is none of its scenes"
      end
      scenes
    end

    # Check one declared scene's name and words, as `scenes` is written.
    def scene!(klass, name, what)
      name = name.to_s
      unless A_SCENE.match?(name) && name != NO_SCENE
        raise DeclarationRefused, "#{klass}: a scene is named in lowercase, and not \"#{NO_SCENE}\": \"#{name}\" is not one"
      end
      raise DeclarationRefused, "#{klass}: the scene #{name} says what it shows, in words" if what.to_s.strip.empty?

      [name, what.to_s]
    end

    # The tool the model moves the screen with: one of the scenes, or `none`.
    def showing_tool(scenes)
      listed = scenes.map { |name, what| "#{name}: #{what}" }.join("; ")
      {
        name: SHOW_SCREEN,
        description: "Put a scene on the caller's screen, or keep the one there, in the same turn as your words. #{listed}; #{NO_SCENE}: nothing chosen.",
        parameters: { type: "object", properties: { scene: { type: "string", enum: [*scenes.keys, NO_SCENE] } }, required: ["scene"] },
        side_effect: "read",
        quiet: true
      }
    end

    # What the model reads of the screen in this turn; empty for a class with no scenes.
    def scene_line(scenes, scene)
      return "" if scenes.empty?
      return "The caller's screen shows no scene. Put one up with #{SHOW_SCREEN} when it helps them." if scene.nil?

      "The caller's screen shows #{scene} (#{scenes.fetch(scene, scene)}). It goes away when you answer about something else; " \
        "call #{SHOW_SCREEN} to keep it or to show another."
    end
  end

  class << self
    # Declare a part of the caller's screen: `Agenda = Pinecall.part("agenda")`.
    def part(name) = Screen.part(name)

    # A task of your own: `Pinecall.task("plate", asks: "…", fields: { plate: "…" }) { |given| … }`.
    def task(name, **spec, &check) = Tasks.task(name, **spec, &check)
  end
end
