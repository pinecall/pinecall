# frozen_string_literal: true

require "test_helper"

# A call being served learns its line and its day off the log alone.
class ClientCallTest < Minitest::Test
  AnAgent = Struct.new(:slug) do
    def on_error(error) = raise(error)
  end

  STARTED = { channel: "web", direction: "inbound", from: "web", to: "front-desk", caller: nil, started_at: 1_786_537_500.0 }.freeze

  def setup
    @call = Pinecall::Client::Call.new("CA_1", AnAgent.new("front-desk"), 1_786_537_500.0)
  end

  def test_a_call_runs_on_the_day_call_started_names_when_a_golden_pinned_one
    @call.take(entry("call.started", STARTED.merge(run: "run_1", today: "2026-09-17")))

    assert_equal "2026-09-17", @call.today
    assert_equal "active", @call.status
  end

  def test_a_call_nobody_pinned_runs_on_the_day_it_opened
    @call.take(entry("call.started", STARTED))

    assert_equal Time.at(1_786_537_500.0).strftime("%Y-%m-%d"), @call.today
  end

  def test_a_call_handed_over_keeps_the_day_its_start_names
    @call.take(entry("call.attached", { app: "app_2", started: STARTED.merge(today: "2026-09-17"), state: { stage: "book" }, seq: 9, claimed: nil }))

    assert_equal "2026-09-17", @call.today
    assert_equal({ stage: "book" }, @call.state)
  end

  private

  def entry(type, data)
    Pinecall::Wire::Entry.new(seq: 1, ts: 1_786_537_500.0, call: "CA_1", agent: "front-desk", type:, ephemeral: false, data:)
  end
end
