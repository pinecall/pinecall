# frozen_string_literal: true

module Pinecall
  # A function that outlives a call. It runs in this process; the gateway keeps its journal, its
  # clock and what wakes it. `Pinecall.flow("remind-visit") { |visit, step| … }`.
  class Flow
    A_NAME = /\A[a-z0-9][a-z0-9-]*\z/
    A_WHILE = /\A(\d+)(s|m|h|d)\z/
    SECONDS = { "s" => 1, "m" => 60, "h" => 3600, "d" => 86_400 }.freeze
    # What a run still waiting is in: the ones an event may cancel.
    WAITING = %w[ready sleeping waiting calling].freeze

    # What a call a flow placed came to; `refused` names why nothing rang.
    Called = Data.define(:answered, :reason, :call, :refused, :message)

    # Where a stretch of a run left it; a failed one says what its function raised.
    Advanced = Data.define(:status, :error)

    # A step could not be written: the run stays as it was, and the gateway hands it out again.
    class StepUnwritten < Error; end

    # The function asked for another step than its journal holds there: its code changed.
    class Changed < Error; end

    # Thrown to leave the function where it waits: not an error.
    class Parked < StandardError; end

    attr_reader :name, :body, :cancels

    def initialize(name, &body)
      raise DeclarationRefused, "a flow's name is lowercase letters, digits and dashes: its runs are kept by it" unless A_NAME.match?(name.to_s)
      raise DeclarationRefused, "#{name}: a flow is a block of what started it and its steps" if body.nil?

      @name = name.to_s
      @body = body
      @cancels = []
    end

    # Cancel the runs still waiting when an event says so: `cancel_on("visit.cancelled") { |gone, visit| … }`.
    def cancel_on(event, &when_)
      @cancels << [event.to_s, when_]
      self
    end

    # Seconds in `"2h"`, `"30m"`, `"45s"`, `"1d"`.
    def self.seconds_of(how_long)
      found = A_WHILE.match(how_long.to_s.strip)
      raise DeclarationRefused, "\"#{how_long}\" is no length of time: a number and s, m, h or d, like 2h" if found.nil?

      found[1].to_i * SECONDS.fetch(found[2])
    end

    # Start a run of the flow; the same key is the same run.
    def started(door, key, input) = Client::AppWork.start_run(door, @name, key, input)

    # Cancel the flow's waiting runs an event names; how many.
    def cancelled(door, event, data)
      asking = @cancels.select { |named, _| named == event.to_s }.map(&:last)
      return 0 if asking.empty?

      WAITING.sum do |status|
        Client::AppWork.runs_of(door, @name, status).count do |run|
          next false unless asking.any? { |when_| when_.call(data, run[:input]) }

          Client::AppWork.cancel_run(door, run[:id])
          true
        end
      end
    end

    # Run the function against the run's journal, one stretch; end the run when it returns.
    def advance(door, run, slug_of)
      @body.call(run[:input] || {}, Step.new(door, self, run, slug_of))
    rescue Parked
      Advanced.new(status: "parked", error: nil)
    rescue StepUnwritten
      raise
    rescue StandardError => e
      error = "#{e.class}: #{e.message}"
      Client::AppWork.end_run(door, run[:id], "failed", error)
      Advanced.new(status: "failed", error:)
    else
      Client::AppWork.end_run(door, run[:id], "done")
      Advanced.new(status: "done", error: nil)
    end

    # The steps of a flow. Each is written to the run's journal and read back on the next run.
    class Step
      def initialize(door, flow, run, slug_of)
        @door = door
        @flow = flow
        @run = run
        @slug_of = slug_of
        @journal = (run[:steps] || []).to_h { |step| [step[:seq], step] }
        @seq = 0
      end

      # Sleep for a while: `"2h"`, `"30m"`, `"45s"`, `"1d"`.
      def sleep(how_long) = waited("sleep", { until: (Time.now.utc + Flow.seconds_of(how_long)).iso8601 }) && nil

      # Sleep until a time, or until `before` it: `step.sleep_until(visit[:at], before: "24h")`.
      def sleep_until(at, before: nil)
        moment = at.is_a?(Time) ? at : Time.iso8601(at.to_s)
        until_ = moment - (before.nil? ? 0 : Flow.seconds_of(before))
        waited("sleep", { until: until_.utc.iso8601 })
        nil
      end

      # Have an agent call a number, and wait for how the call ended.
      def call(to, agent, state: nil, metadata: nil, greeting: nil, instruction: nil, from: nil)
        slug = @slug_of.call(agent)
        raise DeclarationRefused, "#{@flow.name}: #{agent} is no agent this process serves" if slug.nil?

        asked = { agent: slug, to:, state:, metadata:, greeting:, instruction:, from: }.compact
        said = waited("call", asked) || {}
        Called.new(answered: said[:answered] == true, reason: said[:reason], call: said[:call], refused: said[:refused],
                   message: said[:message])
      end

      # Wait for an event of the app whose data has what `match` names; nil when it gave up.
      def wait_for(event, match: nil, within: nil)
        asked = { event:, match: }.compact
        asked[:until] = (Time.now.utc + Flow.seconds_of(within)).iso8601 unless within.nil?
        waited("wait", asked)
      end

      # Run something once: what it returned is kept, and read back instead of run again.
      def run
        before = written("run")
        return before[:result] unless before.nil?

        result = yield
        kept { Client::AppWork.write_step(@door, @run[:id], { seq: @seq, kind: "run", result: Wire::Codec.plain(result) }) }
        result
      end

      # Send an event to the app.
      def emit(name, data = {})
        return unless written("emit").nil?

        kept { Client::AppWork.write_step(@door, @run[:id], { seq: @seq, kind: "emit", asked: { name:, data: } }) }
        nil
      end

      private

      def written(kind)
        @seq += 1
        before = @journal[@seq]
        if !before.nil? && before[:kind] != kind
          raise Changed, "#{@flow.name}: step #{@seq} was a #{before[:kind]} and is now a #{kind}: the flow's code changed under run #{@run[:id]}"
        end

        before
      end

      def waited(kind, asked)
        before = written(kind)
        return before[:result] if !before.nil? && before[:over]
        raise Parked unless before.nil?

        after = kept { Client::AppWork.write_step(@door, @run[:id], { seq: @seq, kind:, asked: }) }
        raise Parked unless after[:status] == "ready"

        read = kept { Client::AppWork.read_run(@door, @run[:id]) }
        (read[:steps] || []).find { |step| step[:seq] == @seq }&.dig(:result)
      end

      # A gateway that did not answer is no failure of the flow: the run is not ended over it.
      def kept
        yield
      rescue Refused, SystemCallError, IOError, Timeout::Error => e
        raise StepUnwritten, e.message
      end
    end
  end

  class << self
    # A flow named once: `RemindVisit = Pinecall.flow("remind-visit") { |visit, step| … }`.
    def flow(name, &body) = Flow.new(name, &body)
  end
end
