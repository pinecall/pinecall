# frozen_string_literal: true

require "test_helper"
require "flows/kept_app"

# A flow: its block run against the journal the gateway keeps, one stretch at a time.
class FlowsTest < Minitest::Test
  # You remind patients of their visit.
  class Reminder < Pinecall::Agent; end

  SLUG_OF = ->(agent) { agent == Reminder ? "brightside-reminder" : nil }

  def setup
    @kept = KeptApp.new
    @door = @kept.door
  end

  def teardown = @kept.stop

  def test_a_flow_is_a_name_and_a_block_and_a_length_of_time_a_number_and_its_unit
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.flow("Remind Visit") { nil } }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.flow("remind-visit") }
    assert_equal [45, 1800, 7200, 86_400], %w[45s 30m 2h 1d].map { |one| Pinecall::Flow.seconds_of(one) }
  end

  def test_a_flow_is_started_once_for_one_key
    remind = Pinecall.flow("remind-visit") { nil }
    first = remind.started(@door, "visit-7", { id: 7 })

    assert_equal first[:id], remind.started(@door, "visit-7", { id: 7 })[:id]
    assert_equal 1, @kept.runs.length
  end

  def test_a_run_is_left_at_a_sleep_and_goes_on_from_it_once_woken
    said = []
    remind = Pinecall.flow("remind-visit") do |visit, step|
      said << "before"
      step.sleep_until(visit[:at], before: "24h")
      said << "after"
    end
    run = remind.started(@door, "visit-7", { at: "2026-11-14T09:30:00Z" })

    assert_equal "parked", remind.advance(@door, run, SLUG_OF).status
    assert_equal "sleeping", @kept.runs[run[:id]][:status]
    assert_equal({ until: "2026-11-13T09:30:00Z" }, @kept.runs[run[:id]][:steps].first[:asked])
    @kept.wake(run[:id], nil)

    assert_equal "done", remind.advance(@door, remind.started(@door, "visit-7", {}), SLUG_OF).status
    assert_equal %w[before before after], said
  end

  def test_an_effect_runs_once_and_is_read_back_after
    sent = []
    remind = Pinecall.flow("remind-visit") do |_visit, step|
      step.run { (sent << 1).length }
      step.sleep("2h")
    end
    remind.advance(@door, remind.started(@door, "visit-7", {}), SLUG_OF)
    @kept.wake("run_1", nil)
    remind.advance(@door, remind.started(@door, "visit-7", {}), SLUG_OF)

    assert_equal [1], sent
  end

  def test_a_call_step_dials_as_the_agents_slug_and_reads_how_it_ended
    ended = []
    remind = Pinecall.flow("remind-visit") { |visit, step| ended << step.call(visit[:phone], Reminder, instruction: "Remind them.") }
    @kept.refuses = { answered: false, refused: "Forbidden", message: "a stranger" }

    assert_equal "done", remind.advance(@door, remind.started(@door, "visit-7", { phone: "+59899000001" }), SLUG_OF).status
    assert_equal({ agent: "brightside-reminder", to: "+59899000001", instruction: "Remind them." }, @kept.runs["run_1"][:steps].first[:asked])
    assert_equal "Forbidden", ended.first.refused
  end

  def test_a_step_the_gateway_could_not_write_leaves_the_run_as_it_was
    remind = Pinecall.flow("remind-visit") { |_visit, step| step.sleep("1h") }
    run = remind.started(@door, "visit-7", {})
    @kept.down = "the database is away"

    assert_raises(Pinecall::Flow::StepUnwritten) { remind.advance(@door, run, SLUG_OF) }
    assert_equal "ready", @kept.runs[run[:id]][:status]
  end

  def test_an_event_cancels_the_waiting_runs_it_names
    remind = Pinecall.flow("remind-visit") { |_visit, step| step.sleep("1h") }
    remind.cancel_on("visit.cancelled") { |gone, visit| gone[:id] == visit[:id] }
    %w[7 8].each { |id| remind.advance(@door, remind.started(@door, "visit-#{id}", { id: id.to_i }), SLUG_OF) }

    assert_equal 1, remind.cancelled(@door, "visit.cancelled", { id: 7 })
    assert_equal %w[cancelled sleeping], @kept.runs.values.map { |run| run[:status] }
  end
end
