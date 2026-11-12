# frozen_string_literal: true

require "test_helper"
require "flows/kept_app"

# The app's loop: an event to its handlers and the flows it starts, a run a stretch further.
class FlowLoopTest < Minitest::Test
  def setup
    @kept = KeptApp.new
    @heard = []
    @reported = []
    remind = Pinecall.flow("remind-visit") { |_visit, step| step.sleep("1h") }
    app = Pinecall.voice_app("brightside")
    app.on("visit.booked") { |_call, data| @heard << data }
    app.on("visit.booked", remind)
    @loop = Pinecall::FlowLoop.new(app, @kept.door, slug_of: ->(_) {}, report: ->(line) { @reported << line })
  end

  def teardown = @kept.stop

  def entry(type, data, ephemeral: false)
    Pinecall::Wire::Entry.new(seq: 4, ts: 1.0, call: "CA_1", agent: "front-desk", type:, ephemeral:, data:)
  end

  def test_an_event_reaches_its_handler_starts_its_flow_once_and_is_heard
    sent = @kept.send_event("visit.booked", { id: 7 })
    @loop.worked_once(0.1)

    assert_equal [{ id: 7 }], @heard
    assert_equal ["remind-visit"], @kept.runs.values.map { |run| run[:flow] }
    assert_equal [sent], @kept.heard
    @loop.worked_once(0.1)

    assert_equal "sleeping", @kept.runs.values.first[:status]
  end

  def test_a_logged_line_starts_its_flow_by_its_own_name_and_a_passing_entry_none
    @loop.entry_heard(entry("custom", { name: "visit.booked", data: { id: 7 } }))
    @loop.entry_heard(entry("custom", { name: "visit.booked", data: { id: 8 } }, ephemeral: true))

    assert_equal [{ id: 7 }], @kept.runs.values.map { |run| run[:input] }
  end

  def test_a_pass_heard_on_a_call_has_it_take_the_teammates_voice
    @loop.pass_heard(entry("custom", { name: "handoff", data: { from: "front-desk", to: "billing" } }))

    assert_equal ['POST /v1/calls/CA_1/stages {"agent":"billing"}'], @kept.asked
    @kept.staged = 500
    @loop.pass_heard(entry("custom", { name: "handoff", data: { to: "billing" } }))

    assert_equal ["CA_1 keeps the voice it had after its pass to billing: 500"], @reported
  end
end
