# frozen_string_literal: true

require_relative "../pinecall"

module Pinecall
  # An in-process fake gateway for offline (ring 0) tests.
  #
  # Answers register/configure, records every command, and lets a test drive calls, tool calls
  # and events.
  #
  #     pc = Pinecall::Testing::Gateway.new
  #     Pinecall.mount(ClinicaNorte, client: pc)
  #     call = pc.call_started(from: "+34600123456")
  #     call.tool("find_patient", name: "Marta Ruiz", phone: "+34600123456")
  #     assert_includes call.prompt, "Marta Ruiz"
  module Testing
    # A call driven by a test.
    class Fake
      attr_reader :id, :gateway

      def initialize(gateway, id)
        @gateway = gateway
        @id = id
      end

      # Simulate a tool call; returns the `tool.result` data.
      def tool(name, **arguments)
        call_id = "tc_#{@gateway.next_seq}"
        @gateway.deliver("tool.call", { call_id:, name: name.to_s, arguments: }, call: @id)
        @gateway.settled { |sent| sent.type == "tool.result" && sent.data[:call_id] == call_id }
      end

      # Deliver an external event from the backend (`from: "app"`) or a participant.
      def fact(name, data = {}, from: "app", identity: nil)
        payload = { name: name.to_s, data:, source: from.to_s }
        payload[:identity] = identity unless identity.nil?
        @gateway.deliver("event.received", payload, call: @id)
        @gateway.settle
      end

      # Deliver a caller turn.
      def said(text)
        @gateway.deliver("turn.user", { text:, speech_id: "sp_#{@gateway.next_seq}", metrics: {} }, call: @id)
        @gateway.settle
      end

      # Deliver `call.ended`.
      def ended(reason: "caller_hung_up")
        @gateway.deliver("call.ended", { reason:, ended_by: "caller", ended_at: Time.now.to_f, duration_s: 1.0 },
                         call: @id)
        @gateway.settle
      end

      # The last `view` block sent.
      def prompt = block("view")

      # The last text sent for a prompt block.
      def block(name) = last("prompt.set", name: name.to_s)&.dig(:text)

      # Names of the currently visible tools.
      def tools = (last("tools.set")&.dig(:tools) || []).map { |spec| spec[:name] }

      # The last state sent.
      def state = last("state.set")&.dig(:state) || {}

      # Commands sent for this call, in order.
      def commands = @gateway.commands.select { |sent| sent.call == @id }

      # Data of the last command of `type` whose fields match `matching`.
      def last(type, **matching)
        commands.reverse.find do |sent|
          sent.type == type && matching.all? { |field, value| sent.data[field] == value }
        end&.data
      end
    end

    # Stands in for `Pinecall::Client` in `Pinecall.mount`.
    class Gateway
      attr_reader :commands, :agents

      def initialize
        @commands = []
        @agents = {}
        @seq = 0
        @errors = []
        @found = []
        @searched = []
      end

      # The chunks every search of this gateway answers with: `{ path:, heading:, text: }`.
      def finds(*chunks)
        @found = chunks
        self
      end

      # Every search asked of this gateway, in order: `{ call:, query:, k: }`.
      attr_reader :searched

      # Same signature as `Pinecall::Client#search`.
      def search(call, query, k: nil)
        @searched << { call:, query:, k: }
        @found
      end

      def sdk = "pinecall-ruby-testing/#{VERSION}"

      # Same signature as `Pinecall::Client#agent`.
      def agent(slug, **options)
        @agents[slug] = Client::Agent.new(slug, options, self)
      end

      # Record a command and answer it if the gateway would.
      def send_command(type:, agent:, call:, data:, id: nil)
        frame = Wire.command(type:, agent:, call:, data:, id:)
        @commands << frame
        answer(frame)
        frame
      end

      def seen(_event, _call) = nil

      def on_error(error)
        @errors << error
        warn("pinecall testing: #{error.class}: #{error.message}")
      end

      # Unhandled errors, for assertions.
      attr_reader :errors

      # Start a call and return its `Fake` handle; `state:` is the state its opener asked for,
      # `today:` the day a golden pinned (YYYY-MM-DD).
      def call_started(id: nil, channel: "web", from: "+34600000000", to: "+34910000000", caller: nil, state: nil,
                       today: nil)
        id ||= "CA_#{next_seq}"
        started = { channel:, direction: "inbound", from:, to:, caller:, started_at: Time.now.to_f }
        started = started.merge(state:) unless state.nil?
        started = started.merge(today:) unless today.nil?
        deliver("call.started", started, call: id)
        settle
        Fake.new(self, id)
      end

      # Hand this process a call mid-conversation, in `state`; returns its `Fake` handle.
      def call_attached(state:, id: nil, from: "+34600000000", claimed: nil)
        id ||= "CA_#{next_seq}"
        started = { channel: "web", direction: "inbound", from:, to: "+34910000000", caller: nil, started_at: Time.now.to_f }
        deliver("call.attached", { app: "app_test", started:, state:, seq: next_seq, claimed: }, call: id)
        settle
        Fake.new(self, id)
      end

      # Deliver an entry to the agent.
      def deliver(type, data, call: nil, agent: @agents.keys.first)
        entry = Wire::Entry.new(seq: next_seq, ts: Time.now.to_f, call:, agent:, type:,
                                    ephemeral: Wire::Codec.ephemeral?(type), data:)
        @agents[agent]&.take(entry)
        entry
      end

      # Wait until the call threads are idle.
      def settle(within_s: 2)
        deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + within_s
        sleep(0.002) while Thread.list.count { |thread| thread.status == "run" } > 1 &&
                           Process.clock_gettime(Process::CLOCK_MONOTONIC) < deadline
        sleep(0.01)
        nil
      end

      # Wait for a command matching the block and return its data.
      def settled(within_s: 2)
        deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + within_s
        loop do
          found = @commands.reverse.find { |sent| yield(sent) }
          return found.data unless found.nil?
          raise Error, "the app never sent it" if Process.clock_gettime(Process::CLOCK_MONOTONIC) > deadline

          sleep(0.005)
        end
      end

      def next_seq = @seq += 1

      # Like the real gateway, only register/configure get a reply.
      def answer(frame)
        case frame.type
        when "agent.register"
          deliver("agent.registered", { app: "app_test", routes: frame.data[:routes] }, agent: frame.agent)
        when "agent.configure"
          deliver("agent.configured", { changed: frame.data[:config].keys.map(&:to_s) }, agent: frame.agent)
        end
      end
    end
  end
end
