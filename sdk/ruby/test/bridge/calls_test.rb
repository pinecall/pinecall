# frozen_string_literal: true

require "test_helper"

# What a class reads of the call it serves: who, where to, which way, and what it was opened with.
class BridgeCallsTest < Minitest::Test
  # Anota la línea.
  class Anotadora < Pinecall::Agent
    state :line

    def on_call(call)
      self.line = { from: call.from, to: call.to, direction: call.direction, caller: call.caller, metadata: call.metadata }
    end
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Anotadora, client: @gateway)
  end

  def test_the_call_says_where_it_went_which_way_and_what_it_was_opened_with
    marta = { id: "ct_7d1e", phone: "+34600123456", name: "Marta Ruiz" }
    call = @gateway.call_started(from: "+34910000001", to: "+34600123456", direction: "outbound", caller: marta,
                                 metadata: { campaign: "revision-anual" })

    assert_equal({ from: "+34910000001", to: "+34600123456", direction: "outbound", caller: marta,
                   metadata: { campaign: "revision-anual" } }, call.state[:line])
  end

  def test_a_call_opened_with_nothing_names_nobody_and_has_no_metadata
    call = @gateway.call_started

    assert_equal({ from: "+34600000000", to: "+34910000000", direction: "inbound", caller: nil, metadata: {} },
                 call.state[:line])
  end

  def test_a_call_handed_over_keeps_what_it_was_opened_with
    call = @gateway.call_attached(state: {}, from: "+34600123456")

    assert_equal "+34910000000", @gateway.agents.values.first.calls.live.find { |one| one.id == call.id }.to
  end
end
