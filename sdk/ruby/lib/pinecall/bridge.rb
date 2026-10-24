# frozen_string_literal: true

module Pinecall
  # Mounts an agent class on a client, with one instance per call. The only module that knows
  # both the agent and the socket.
  module Bridge
    # A mounted agent and its live instances.
    class Mounted
      attr_reader :slug, :agent, :options

      def initialize(slug:, agent:, options:, live:)
        @slug = slug
        @agent = agent
        @options = options
        @live = live
      end

      # The instance serving `call_id`, or nil.
      def serving(call_id) = @live[call_id]&.agent
    end

    # One served call: its instance, what was last sent, and a thread running its jobs in order.
    class Live
      attr_reader :agent, :world, :sent, :stops
      # What memory recalled about this caller in this call: what `remembers?` answers from; and whether
      # the call was handed over mid-conversation, the view's `resumed`.
      attr_accessor :tools_shown, :remembered, :resumed

      def initialize(agent, world)
        @agent = agent
        @world = world
        @sent = {}
        @tools_shown = nil
        @remembered = []
        @resumed = false
        @stops = {}
        @work = Thread::Queue.new
        @thread = Thread.new { work }
      end

      # Queue a job; jobs run one at a time in order, which keeps `world.cause` accurate.
      def later(&job) = @work << job

      def finish
        @work << :done
        @thread.join(5)
      end

      private

      def work
        while (job = @work.pop)
          break if job == :done

          begin
            job.call
          rescue StandardError => e
            warn("pinecall: #{e.class}: #{e.message}")
          end
        end
      end
    end

    module_function

    # Mount a class on a client; each call gets its own instance. Nothing is sent until `connect`.
    #
    # @param last [Proc] source for `last(contact)`
    # @param takes_unclaimed [Boolean] false for a console, which serves only calls it opens
    def mount(klass, client:, slug: nil, last: nil, takes_unclaimed: true)
      name = slug || klass.slug
      live = {}
      # Throwaway instance used only to read the class's declarations.
      probe = klass.new
      options = klass.wire_config(tools: tools_for(probe, live)).merge(takes_unclaimed:, says_done: true)
      agent = client.agent(name, **options)
      agent.on("call.started") { |started, call| start(klass, live, call, client, last, started[:state]) }
      agent.on("call.attached") { |_data, call| attached(klass, live, call, client, last) }
      agent.on("call.ended") { |_data, call| finish(live, call) }
      Mounted.new(slug: name, agent:, options:, live:)
    end

    # Tool specs with a `run` routed to the instance serving the calling call.
    def tools_for(probe, live)
      probe.tools.map do |spec|
        spec.merge(run: lambda do |arguments, call, call_id|
          serving = live[call.id]
          raise ToolFailed, "#{spec[:name]}: this call is no longer being served" if serving.nil?

          serving.agent.run_tool(spec[:name], arguments, call_id)
        end)
      end
    end

    # A call handed to this process mid-conversation: no `on_call`, the state the gateway kept
    # instead. One served here already (the gateway restarted) keeps its instance, and its whole
    # prompt is sent again, which the gateway may have lost.
    def attached(klass, live, call, client, last)
      held = live[call.id]
      return held.later { resend(held, call) } unless held.nil?

      instance = klass.new.seal
      instance.reads_last_from(last) unless last.nil?
      serving = Live.new(instance, world_for(call, client))
      serving.resumed = true
      instance.serving(serving.world)
      live[call.id] = serving
      serving.later do
        forward_log(serving, call)
        instance.restore(call.state)
        sync(serving, call)
        listen(serving, call)
      end
    end

    def resend(serving, call)
      serving.sent.clear
      serving.tools_shown = nil
      sync(serving, call)
    end

    def world_for(call, client)
      searching = ->(query, k) { client.search(call.id, query, k:) }
      CallWorld.new(id: call.id, contact: call.contact&.dig(:id) || call.from, from: call.from, to: call.to,
                    channel: call.channel, direction: call.direction, caller: call.contact, metadata: call.metadata,
                    medium: call.medium, today: call.today, claimed: call.claimed, searching:) do |type, data|
        call.command(type, data)
      end
    end

    # Build the instance and run `on_call` before listening, so the first prompt is sent once
    # rather than once per field. The state the opener asked for (`call.started.state`) is applied
    # after the hook, which would overwrite it, and before the first render. The log is open from the
    # hook on: a line `on_call` writes is the call's.
    def start(klass, live, call, client, last, opened_in)
      instance = klass.new.seal
      instance.reads_last_from(last) unless last.nil?
      world = world_for(call, client)
      instance.serving(world)
      serving = Live.new(instance, world)
      live[call.id] = serving
      serving.later do
        forward_log(serving, call)
        hooked(serving, call, :on_call, world)
        instance.start_in(opened_in) unless opened_in.nil?
        call.set_state(instance.snapshot, *opening(instance))
        sync(serving, call)
        listen(serving, call)
      end
    end

    # What the opening `state.set` says: when `on_call` wrote, the fields written and the hook as the
    # cause. Nothing written, nothing said: the whole state is the news.
    def opening(instance)
      return [] unless instance.changes.any? { |change| change.author == "hook:on_call" }

      [instance.changes.map(&:field).uniq, { kind: "hook", hook: "on_call" }]
    end

    # Re-sync the prompt on every state change, each one sent with who wrote it.
    def listen(serving, call)
      instance = serving.agent
      serving.stops[:state] = instance.on_change do |change|
        call.set_state(instance.snapshot, [change.field], cause_of(change, serving))
        sync(serving, call)
      end
      serving.stops[:entries] = call.on_any do |event|
        serving.world.take(event.type, event.data, Time.now.to_f)
        received(serving, call, event) if event.type == "event.received"
        rerendered(serving, call, event)
      end
    end

    # Who made a write, as the wire's `StateCause` says it: the lifecycle hook, the outside fact the hook is
    # handling, or the tool and the model's id for the call that ran it. A write the wire has no word for
    # (a restore) says nothing.
    def cause_of(change, serving)
      author = change.author.to_s
      case author
      when "hook:on_call", "hook:on_memory" then { kind: "hook", hook: author.delete_prefix("hook:") }
      when "hook:on_event" then (fact = serving.world.cause) && { kind: "event", **fact }
      else
        call_id = Agent::Author.call_id
        { kind: "tool", tool: author, call_id: } if call_id && serving.agent.class.tool_named(author)
      end
    end

    # What the class logs reaches the call's log until `on_end` has run.
    def forward_log(serving, call)
      serving.stops[:log] = serving.agent.on_log { |entry| call.log(entry.name, as_object(entry.data)) }
    end

    # The view answers the turn being taken, not the one before it; a claim lets the caller see the
    # page; recall is not state, so nothing else would render what it brought. What memory did then
    # reaches `on_memory`, after the view already says it.
    def rerendered(serving, call, event)
      case event.type
      when "turn.user", "call.claimed" then sync(serving, call)
      when "memory.ops"
        serving.remembered = words_recalled(event.data)
        sync(serving, call)
        serving.later { hooked(serving, call, :on_memory, event.data[:ops] || [], serving.world) }
      end
    end

    # Each recalled fact's text and category; a `remember` op stores this call's facts, it surfaces none.
    def words_recalled(data)
      (data[:ops] || []).select { |op| op[:op] == "recall" }.flat_map do |op|
        (op[:facts] || []).flat_map { |fact| [fact[:text], fact[:category] || ""] }
      end
    end

    # Drop events whose (name, source) the class did not declare: an `:app` event arriving from
    # a browser could be spoofed.
    def received(serving, call, event)
      fact = event.data
      name = fact[:name].to_s
      allowed = agent_class(serving).declared_events[name]
      unless allowed&.include?(fact[:source].to_s)
        return warn("pinecall: #{name} from #{fact[:source]} is not declared by this agent")
      end

      meta = { source: fact[:source], identity: fact[:identity], seq: event.seq }.compact
      serving.later do
        serving.world.cause = { name:, seq: event.seq }
        begin
          hooked(serving, call, :on_event, name, fact[:data] || {}, meta, event: name)
          serving.agent.notify_heard(name, fact[:data] || {}, meta)
        ensure
          serving.world.cause = nil
        end
      end
    end

    # Stop rendering and reading entries; the log stays open until `on_end` has run.
    def finish(live, call)
      serving = live.delete(call.id)
      return if serving.nil?

      serving.stops.values_at(:state, :entries).compact.each(&:call)
      serving.later do
        hooked(serving, call, :on_end, serving.world)
        serving.stops[:log]&.call
        # After every line the hook logged, whether it ran or raised: the gateway seals the call on this
        # word, and a line sent after the seal is refused.
        call.done
      end
      serving.finish
    end

    # Send only blocks whose text changed since this call's last send: identical re-sends waste
    # the provider's prompt cache. Unsent blocks count as empty.
    def sync(serving, call)
      line = { channel: call.channel || "web", from: call.from, claimed: serving.world.claimed }
      begin
        rendered = Prompt.render(serving.agent, resumed: serving.resumed, remembered: serving.remembered, line:)
        visible = serving.agent.visible_tools
      rescue StandardError => e
        return failed_to_render(call, e)
      end
      rendered.blocks.each do |block|
        next if block.text == serving.sent.fetch(block.name, "")

        serving.sent[block.name] = block.text
        call.set_prompt(block.name, block.text)
      end
      return if visible == serving.tools_shown

      serving.tools_shown = visible
      call.set_tools(visible)
    end

    # A view that fails fails its call, never the process: the model keeps the view it had, and the log says why.
    def failed_to_render(call, error)
      said = failure_of(error)
      call.log("render.failed", { error: error.class.to_s, message: said })
      warn("pinecall: #{call.id} could not render its view and goes on with the one it had: #{said}")
    end

    # A NameError's message is Ruby's, with the view's whole context inspected, its state's private values
    # among them (R F6): the name it missed is the sentence, which a person can act on.
    def failure_of(error)
      case error
      when NoMethodError then "the view calls #{error.name}, which nothing it reads answers"
      when NameError then "the view names #{error.name}, which is no field of the state, no call and no method of the class"
      else error.message
      end
    end

    # A hook that raises fails its call, never the process: the call goes on with what the hook wrote
    # before it raised, and the log says which hook and why.
    def hooked(serving, call, hook, *args, event: nil)
      serving.agent.run_hook(hook, *args)
    rescue StandardError => e
      call.log("hook.failed", { hook: hook.to_s, event:, error: e.class.to_s, message: e.message }.compact)
      warn("pinecall: #{call.id} #{hook} raised and the call goes on without it: #{e.message}")
      nil
    end

    def agent_class(serving) = serving.agent.class

    # `call.log` data must be an object: a `Data` or a `Struct` is its fields, other values go under `value`.
    def as_object(data)
      fields = Wire::Codec.plain(data)
      return {} if fields.nil?

      fields.is_a?(Hash) ? fields : { value: fields }
    end
  end
end
