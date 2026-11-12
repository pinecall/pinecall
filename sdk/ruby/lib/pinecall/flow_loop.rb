# frozen_string_literal: true

module Pinecall
  # The loop a voice app keeps with the gateway: the events it is owed heard, its flows' runs advanced.
  class FlowLoop
    # How long one ask for work waits at the gateway.
    WAITS_S = 20
    # How long the loop rests after a gateway that did not answer.
    RESTS_S = 5
    # A written call has no worker to tell (404), and one that ended has none either (409).
    NOTHING_TO_RESTAGE = [202, 404, 409].freeze
    FAILED = [Refused, SystemCallError, IOError, Timeout::Error].freeze

    attr_reader :app, :door

    # `slug_of` names the slug each class is served as; `report` says a failure, one line each.
    def initialize(app, door, slug_of:, report:)
      @app = app
      @door = door
      @slug_of = slug_of
      @report = report
    end

    # An entry of that name starts each flow `app.on` gave it, once by `key`, and cancels the runs it names.
    def flows_heard(name, data, key)
      @app.started_by(name).each do |flow|
        flow.started(@door, key, data)
      rescue *FAILED => e
        @report.call("#{flow.name} was not started by #{name}: #{e.message}")
      end
      @app.flows.each do |flow|
        flow.cancelled(@door, name, data)
      rescue *FAILED => e
        @report.call("#{flow.name} was not cancelled by #{name}: #{e.message}")
      end
    end

    # The same for an entry of a call's log; one that is not kept starts nothing.
    def entry_heard(entry)
      return if entry.ephemeral

      name, data = @app.named(entry.type, entry.data)
      flows_heard(name, data, "#{entry.call || entry.agent}:#{entry.seq}")
    end

    # A call passed to a teammate takes that agent's model and voice from the gateway.
    def pass_heard(entry)
      name, data = @app.named(entry.type, entry.data)
      to = data[:to]
      return unless name == Handoff::PASSED && !entry.call.nil? && to.is_a?(String)

      status = Client::AppWork.staged_as(@door, entry.call, to)
      @report.call("#{entry.call} keeps the voice it had after its pass to #{to}: #{status}") unless NOTHING_TO_RESTAGE.include?(status)
    rescue SystemCallError, IOError => e
      @report.call("#{entry.call} keeps the voice it had after its pass to #{to}: #{e.message}")
    end

    # Take what the app is owed once: each event to its handlers and its flows, each run one stretch further.
    def worked_once(wait_s = WAITS_S)
      owed = Client::AppWork.take_work(@door, wait_s)
      (owed[:events] || []).each do |event|
        @app.heard(event[:name], nil, "", event[:data] || {}, ->(name, error) { @report.call("the handler of #{name} raised: #{error.message}") })
        flows_heard(event[:name], event[:data] || {}, "event:#{event[:id]}")
        Client::AppWork.event_heard(@door, event[:id])
      end
      (owed[:runs] || []).map { |run| Thread.new { stretched(run) } }.each(&:join)
    end

    # Keep taking work until `stop`; a gateway away is one line per outage.
    def start
      @thread = Thread.new do
        said = false
        loop do
          worked_once
          said = false
        rescue *FAILED => e
          @report.call("flows: #{e.message}") unless said
          said = true
          sleep(RESTS_S)
        end
      end
      self
    end

    # Stop taking work.
    def stop = @thread&.kill

    private

    def stretched(run)
      flow = @app.flows.find { |one| one.name == run[:flow] }
      # Another release of the app may know the flow: the run is left for it.
      return @report.call("run #{run[:id]} is of the flow #{run[:flow]}, which this app does not have") if flow.nil?

      ended = flow.advance(@door, run, @slug_of)
      @report.call("#{run[:flow]} #{run[:id]} failed: #{ended.error}") if ended.status == "failed"
    rescue Flow::StepUnwritten, *FAILED => e
      @report.call("#{run[:flow]} #{run[:id]}: #{e.message}")
    end
  end
end
