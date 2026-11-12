# frozen_string_literal: true

module Pinecall
  # What a tool call does on a served call, and one agent of a team taking the call from another.
  module Bridge
    module_function

    # A task given, the screen moved, the call passed, or one of the agent's own tools run.
    def dispatched(serving, name, arguments, call_id)
      return serving.asking.given(name, arguments) if serving.asking.gives?(name)
      return Screened.scene_chosen(serving.world, serving.screened, serving.klass, arguments[:scene]) if name == Screen::SHOW_SCREEN

      declared = serving.klass.tool_named(name)
      mate = declared.nil? && !serving.team.nil? ? Handoff.mate_named(name, serving.team) : nil
      return serving.world.handoff(mate, arguments) unless mate.nil?
      raise ToolFailed, "#{name}: this agent declares no such tool" if declared.nil?

      serving.asking.run(name) { showing(serving, declared, arguments, call_id) }
    end

    # Run a tool; one that shows a scene keeps it through the turn, and puts it up once it returns.
    def showing(serving, declared, arguments, call_id)
      scene = declared.options[:shows]
      serving.screened.kept = true unless scene.nil?
      result = Agent::Tools.run(serving.agent, declared, arguments, call_id)
      serving.world.scene = scene.to_s unless scene.nil?
      result
    end

    # The call is served by an instance of `klass` from now on; the call itself stays.
    def become(serving, klass, call, instance = nil)
      instance ||= klass.new.seal
      instance.reads_last_from(serving.last) unless serving.last.nil?
      instance.serving(serving.world)
      serving.agent = instance
      serving.klass = klass
      serving.transfers = Handoff.transfers_of(klass, serving.team) unless serving.team.nil?
      forward_log(serving, call)
    end

    # One agent of the team takes the call from another; the model is told whose it is now.
    def passed(serving, call, to, data)
      slug = serving.team&.[](to)
      raise ToolFailed, "#{to} is not of this call's team" if slug.nil?
      raise ToolFailed, "this call was passed #{Handoff::MOST_PASSES} times already: answer the caller yourself" if serving.passes >= Handoff::MOST_PASSES

      serving.stops.values_at(:state, :entries, :log).compact.each(&:call)
      serving.stops.clear
      serving.agent.serving(nil)
      handed = as_object(data)
      call.log(Handoff::PASSED, { from: serving.team.fetch(serving.klass, ""), to: slug, **handed })
      serving.world.handed = handed
      serving.world.scene = nil
      become(serving, to, call)
      serving.passes += 1
      hooked(serving, call, :on_call, serving.world)
      call.set_state(state_of(serving))
      sync(serving, call)
      listen(serving, call)
      "The call is #{slug}'s now: go on as #{slug}, without saying it was passed."
    end

    # The line chooses while the caller hears its greeting; a choice it could not make is said on the log.
    def routed(serving, call, answers)
      first = Handoff.answered_by(answers, serving.world, serving.klass, serving.team)
      if first.agent != serving.klass || !first.why.nil?
        call.log(Handoff::ROUTED, { to: serving.team.fetch(first.agent, ""), why: first.why }.compact)
      end
      return if first.agent == serving.klass

      serving.stops.delete(:log)&.call
      become(serving, first.agent, call)
    end

    # The call's state as the gateway is told it: the agent's own, and its screen once drawn.
    def state_of(serving) = Screened.state_with(serving.agent.snapshot, serving.screened)

    # The page answered a task: the waiting tool goes on, the model is told, the form drawn again.
    def given_by_page(serving, call, data)
      told = serving.asking.given_by_page(data[:task], data[:given])
      serving.world.reply(told) unless told.nil?
      sync(serving, call)
    end
  end
end
