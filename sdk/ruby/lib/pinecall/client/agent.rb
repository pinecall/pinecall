# frozen_string_literal: true

module Pinecall
  class Client
    # The socket-level handle for one agent slug: its declaration, tool runners and listeners.
    # (`Pinecall::Agent` is the class a developer writes; `Bridge` connects the two.)
    #
    # The gateway's registry is in memory, so the declaration is re-sent on every reconnect.
    # Several sockets may hold one slug; unclaimed calls go to the newest that `takes_unclaimed`,
    # so a rolling deploy serves immediately and a console never gets calls it did not open.
    class Agent
      ANSWERS_WITHIN_S = 10

      NO_DEV_HANDLER = "this process answers no dev verbs: it is not a `pinecall start` in the agent's directory"

      attr_reader :slug, :calls, :config, :app

      def initialize(slug, options, client)
        @slug = slug
        @client = client
        @routes = options[:routes] || []
        @takes_unclaimed = options.fetch(:takes_unclaimed, true)
        @tools = {}
        @waiting = []
        @config = options.reject { |key, _| %i[routes tools takes_unclaimed].include?(key) }
        @app = nil
        @running = []
        @dev = nil
        @lock = Mutex.new
        declare(options[:tools] || [])
        @calls = CallBook.new(self)
        @listeners = Listeners.new { |error| on_error(error) }
      end

      # Listen for one event type across this agent's calls.
      def on(type, &listener) = @listeners.on(type, &listener)

      # Listen for every event of this agent.
      def on_any(&listener) = @listeners.on_any(&listener)

      # Answer the console's `dev.request` asks: the block takes the verb and its data and returns the
      # answer, or raises `DevRefused` to refuse with a status. Without one every ask is a 501.
      def on_dev(&handler)
        @dev = handler
      end

      # Replace the tools; sent with the next `configure`.
      #
      # A tool is `{ **spec, run: ->(arguments, call) { … } }`.
      def declare(tools)
        @tools = tools.to_h { |tool| [tool[:name].to_s, tool] }
        @config = @config.merge(tools: tools.map { |tool| tool.reject { |key, _| key == :run } })
      end

      # Update the agent config. Only the given fields change; live calls keep their session.
      def configure(changes = {})
        @config = @config.merge(changes)
        ask("agent.configure", lands_as: "agent.configured", data: { config: @config })
      end

      # Register the slug and send the config. Runs on every reconnect.
      def open
        registered = ask("agent.register", lands_as: "agent.registered", data: {
                           routes: @routes, sdk: @client.sdk, host: Socket.gethostname,
                           takes_unclaimed: @takes_unclaimed
                         })
        # Each connection gets a new app id.
        @app = registered[:app]
        configure
        self
      end

      # ── called by the client ───────────────────────────────────────────────

      # Apply an entry to its call and notify listeners.
      def take(entry)
        event = Wire.event_of(entry)
        call = entry.call.nil? ? nil : @calls.of(entry.call, entry.ts)
        settle(event)
        call&.take(event)
        @listeners.emit(event, call)
        @client.seen(event, call)
        return answer_the_console(event.data) if event.type == "dev.request"
        return if call.nil?

        run_tool(event, call) if event.type == "tool.call"
        @calls.forget(call)
      end

      def command(type, call, data)
        @client.send_command(type:, agent: @slug, call:, data:, id: "#{@slug}:#{type}")
      end

      def on_error(error) = @client.on_error(error)

      # Agent-scoped heartbeat; answered with `pong`.
      def ping = command("ping", nil, {})

      # Stop taking new calls and hand the live ones to another holder, or park them for the next.
      # Running tools still answer. Returns where the calls went: `{ handed:, parked: }`.
      def drain(answer_s: ANSWERS_WITHIN_S) = ask("agent.drain", lands_as: "agent.draining", data: {}, within_s: answer_s)

      # How many tool runs have not sent their `tool.result` yet.
      def in_flight = @lock.synchronize { @running.count(&:alive?) }

      # Wait until every running tool has answered, or `within_s` passed.
      def settled(within_s: nil)
        deadline = within_s && (now + within_s)
        @lock.synchronize { @running.dup }.each { |thread| thread.join(deadline && [deadline - now, 0].max) }
        nil
      end

      private

      # Always answer with exactly one `tool.result`: without one the turn waits forever.
      # Runs on its own thread so a slow tool does not block the socket reader.
      def run_tool(event, call)
        call_id, name, arguments = event.data.values_at(:call_id, :name, :arguments)
        tool = @tools[name.to_s]
        return call.tool_result({ call_id:, name:, error: "this app declares no tool called #{name}" }) if tool.nil?

        running = Thread.new do
          started = now
          begin
            output = tool[:run].call(arguments || {}, call)
            call.tool_result({ call_id:, name:, output:, duration_s: now - started })
          rescue StandardError => e
            # Report the exception to the model as the tool's `error`.
            call.tool_result({ call_id:, name:, error: e.message, duration_s: now - started })
          end
        end
        @lock.synchronize { (@running << running).select!(&:alive?) }
      end

      # Every ask needs one answer, or the console's request hangs until the gateway gives up. On a
      # thread of its own: a panel reads the tenant's systems, and this is the socket's reader.
      def answer_the_console(asked)
        id, verb, data = asked.values_at(:id, :verb, :data)
        Thread.new do
          raise DevRefused.new(501, NO_DEV_HANDLER) if @dev.nil?

          command("dev.answer", nil, { id:, result: @dev.call(verb, data || {}) })
        rescue DevRefused => e
          command("dev.answer", nil, { id:, refused: { status: e.status, detail: e.detail } })
        rescue StandardError => e
          command("dev.answer", nil, { id:, refused: { status: 500, detail: e.message } })
        end
      end

      # Await the reply event, or an `error` carrying our id. Only register/configure are awaited;
      # other commands are fire-and-forget.
      def ask(type, lands_as:, data:, within_s: ANSWERS_WITHIN_S)
        id = "#{@slug}:#{type}"
        answer = Thread::Queue.new
        @waiting << { type: lands_as, id:, answer: }
        @client.send_command(type:, agent: @slug, call: nil, data:, id:)
        settled = answer.pop(timeout: within_s)
        raise NotConnected, "#{type}: the gateway did not answer in #{within_s}s" if settled.nil?
        raise settled if settled.is_a?(Exception)

        settled
      ensure
        @waiting.reject! { |one| one[:answer].equal?(answer) }
      end

      def settle(event)
        @waiting.dup.each do |waiting|
          if event.type == waiting[:type]
            waiting[:answer].push(event.data)
          elsif event.type == "error" && event.data[:id] == waiting[:id]
            waiting[:answer].push(Refused.new(event.data))
          end
        end
      end

      def now = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    end
  end
end
