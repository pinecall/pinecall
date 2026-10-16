# frozen_string_literal: true

require "cgi"
require "net/http"
require "openssl"
require "socket"
require "uri"
require "websocket/driver"

require_relative "client/endpoints"
require_relative "client/listeners"
require_relative "client/connection"
require_relative "client/call"
require_relative "client/agent"
require_relative "client/observe"
require_relative "client/rest"

module Pinecall
  # A connection to the Pinecall gateway: one socket, its agents, log reads, and a search for a call
  # it serves. `Pinecall::Agent` is built on top of it.
  #
  #     pc = Pinecall::Client.new(url: "https://cloud.pinecall.io", api_key: ENV.fetch("PINECALL_KEY"))
  #     agent = pc.agent("clinica-norte", tools: [])
  #     agent.on("turn.user") { |data, call| call.say("Le he oído: #{data[:text]}") }
  #     pc.connect
  #
  # It reads nothing from the environment: the app hands it the gateway and the key it keeps, and
  # `env: "production"` names production for a person's key (a server's token needs none).
  class Client
    # The `sdk` field sent on register.
    def sdk = "pinecall-ruby/#{VERSION}"

    # A stop from the org: the socket is closed for good and the app decides what comes next.
    STOPPED = "stopped"

    # Seconds the running tools are given to answer once a drain was asked.
    TOOLS_FINISH_WITHIN_S = 30

    # Where a drain sent the calls, and what became of the tools running then.
    Drained = Data.define(:handed, :parked, :tools, :finished)

    attr_reader :url, :api_key, :env

    def initialize(url:, api_key:, env: nil, ping_every: Connection::PINGS_EVERY_S, backoff: {})
      raise ArgumentError, "Pinecall::Client.new(url:, api_key:): one of the two was not given" if url.nil? || api_key.nil?

      @url = url
      @api_key = api_key
      @env = env
      @agents = {}
      @errors = []
      @entries = []
      @stops = []
      @connects = []
      @listeners = Listeners.new { |error| on_error(error) }
      @connection = Connection.new(
        url:, api_key:, env:, ping_every:, backoff:,
        handlers: Connection::Handlers.new(
          on_open: -> { opened },
          on_entry: ->(entry) { took(entry) },
          on_error: ->(error) { on_error(error) },
          on_heartbeat: -> { @agents.each_value { |agent| guarded { agent.ping } } }
        )
      )
    end

    # Declare an agent. Nothing is sent until `connect`.
    def agent(slug, **options)
      @agents[slug] = Agent.new(slug, options, self)
    end

    # Declared agents by slug.
    def agents = @agents.dup

    # Open the socket and register every agent.
    def connect
      @connection.start
      self
    end

    # Close the socket without reconnecting; agents are unregistered.
    def close = @connection.close

    # Leave without cutting calls: each agent drains (its live calls go to another holder, or wait
    # for the next one) and the tools running get up to `tools_s` to answer. Close afterwards.
    def drain(answer_s: Agent::ANSWERS_WITHIN_S, tools_s: TOOLS_FINISH_WITHIN_S)
      @connection.leaving!
      return Drained.new(handed: 0, parked: 0, tools: 0, finished: 0) unless connected?

      answers = @agents.values.filter_map { |agent| guarded { drained(agent, answer_s) } }
      running = @agents.values.sum(&:in_flight)
      deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + tools_s
      @agents.each_value { |agent| agent.settled(within_s: [deadline - Process.clock_gettime(Process::CLOCK_MONOTONIC), 0].max) }
      Drained.new(handed: answers.sum { |one| one[:handed] }, parked: answers.sum { |one| one[:parked] },
                  tools: running, finished: running - @agents.values.sum(&:in_flight))
    end

    # Every entry the socket receives, as the gateway wrote it, before any agent takes it — other
    # agents' entries and the client's own errors included. Returns a lambda that unsubscribes.
    def on_entries(&listener)
      @entries << listener
      -> { @entries.delete(listener) }
    end

    # Called each time the socket is up and every agent on it registered: the first connect and every
    # reconnect after a drop. Returns a lambda that unsubscribes.
    def on_connected(&listener)
      @connects << listener
      -> { @connects.delete(listener) }
    end

    # Called when a member of the org stops this app: the socket is closed for good. Returns a
    # lambda that unsubscribes.
    def on_stopped(&listener)
      @stops << listener
      -> { @stops.delete(listener) }
    end

    # True while the socket is up.
    def connected? = @connection.open?

    # Listen for one event type across all agents.
    def on(type, &listener) = @listeners.on(type, &listener)

    # Listen for every event across all agents.
    def on_any(&listener) = @listeners.on_any(&listener)

    # Listen for unhandled errors (bad frames, raising tools, socket loss). Without a listener
    # they go to stderr. Returns a lambda that unsubscribes.
    def on_errors(&listener)
      @errors << listener
      -> { @errors.delete(listener) }
    end

    # Stream a log, reduced by the wire's reducer. `target` is `{ call: "CA_1" }` or `{ agent: … }`.
    def observe(target, **options, &block) = Observe.observe(target, url: @url, api_key: @api_key, **options, &block)

    # Fetch one page of a log and its reduced state.
    def history(target, **options) = Observe.history(target, url: @url, api_key: @api_key, **options)

    # Search the agent's knowledge bases on behalf of a call this client serves; the gateway runs
    # the search and logs it. Returns the chunks as the gateway answered them.
    def search(call, query, k: nil)
      input = k.nil? ? { query: } : { query:, k: }
      answer = Rest.post(Endpoints.lookup(@url, call), { tool: "search", input: }, api_key: @api_key, env: @env)
      answer.dig(:output, :chunks) || []
    end

    # ── used by agents ───────────────────────────────────────────────────────

    # Send one command, validated against its schema.
    def send_command(type:, agent:, call:, data:, id: nil)
      @connection.send_frame(Wire.command(type:, agent:, call:, data:, id:))
    end

    # Forward an event to client-wide listeners.
    def seen(event, call) = @listeners.emit(event, call)

    def on_error(error)
      return warn("pinecall: #{error.class}: #{error.message}") if @errors.empty?

      @errors.each { |listener| listener.call(error) }
    end

    private

    def took(entry)
      @entries.each { |listener| guarded { listener.call(entry) } }
      return stopped(entry.data[:message]) if stop?(entry)

      agent = @agents[entry.agent]
      # The socket may carry entries for agents this client did not declare.
      return if agent.nil?

      guarded { agent.take(entry) }
    end

    # An `error` coded `stopped` for no agent: a member of the org pressed Stop.
    def stop?(entry) = entry.type == "error" && entry.agent.to_s.empty? && entry.data[:code] == STOPPED

    # With no stop listener the stop is reported as an error, so it is never silent.
    # Every agent registered again, then whoever asked to know.
    def opened
      @agents.each_value(&:open)
      @connects.each { |listener| guarded { listener.call } }
    end

    def stopped(why)
      @connection.close
      return on_error(NotConnected.new(why)) if @stops.empty?

      @stops.each { |listener| guarded { listener.call(why) } }
    end

    # The socket can close between `connected?` and the ask: then nothing was left to hand over. A
    # gateway still connected that never answered is still said.
    def drained(agent, answer_s)
      agent.drain(answer_s:)
    rescue NotConnected
      raise if connected?

      nil
    end

    def guarded
      yield
    rescue StandardError => e
      on_error(e)
      nil
    end
  end
end
