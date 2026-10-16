# frozen_string_literal: true

require "test_helper"

# The call as an agent holds it: each verb one command, and the verbs that wait answered by the log.
class CallWorldTest < Minitest::Test
  def setup
    @sent = []
    @world = world
  end

  def world(**line, &searching)
    Pinecall::CallWorld.new(id: "CA_1", today: "2026-10-07", searching:, **line) do |type, data|
      @sent << [type, Pinecall::Wire::Validate.call!(Pinecall::Wire::Registry::COMMANDS.fetch(type), data, where: type)]
    end
  end

  # Answers the verb waiting on another thread, as the reader thread would.
  def answered_by(type, data)
    Thread.new do
      sleep(0.01) until @sent.any?
      @world.take(type, data, 1.0)
    end
  end

  def test_a_transfer_the_far_end_answered_says_so
    answered_by("call.transferred", { to: "+34910", mode: "cold", ok: true })

    transferred = @world.transfer("+34910")

    assert_equal ["call.transfer", { to: "+34910" }], @sent.first
    assert transferred.ok
    assert_equal "cold", transferred.mode
  end

  def test_a_transfer_nobody_answers_says_the_runtime_never_said
    stub_const(:TRANSFER_WITHIN_S, 0.05) do
      transferred = @world.transfer("+34910", mode: :warm)

      assert_equal ["call.transfer", { to: "+34910", mode: "warm" }], @sent.first
      refute transferred.ok
      assert_equal Pinecall::CallWorld::NO_ANSWER, transferred.error
    end
  end

  def test_attention_waits_for_the_supervisor_who_takes_the_line
    answered_by("attention.answered", { ok: true, by: { id: "sup_1", name: "Lucía" } })

    attended = @world.attention("a refund", wait_s: 30)

    assert_equal ["call.attention", { reason: "a refund", wait_s: 30 }], @sent.first
    assert attended.ok
    assert_equal "Lucía", attended.by[:name]
  end

  def test_hold_unhold_and_dtmf_are_one_command_each
    @world.hold
    @world.unhold
    @world.dtmf("12#")

    assert_equal [["call.hold", {}], ["call.unhold", {}], ["call.dtmf", { digits: "12#" }]], @sent
  end

  def test_a_claim_is_claimed_only_when_the_log_says_it_took
    @world.claim("4821")

    assert_nil @world.claimed
    @world.take("call.claimed", { code: "4821", via: "agent" }, 1.0)
    assert_equal "4821", @world.claimed
  end

  def test_a_code_that_is_not_four_digits_never_reaches_the_wire
    assert_raises(Pinecall::Wire::WireError) { @world.claim("48") }
    assert_empty @sent
  end

  def test_a_callback_carries_when_it_was_asked_for_under_the_wires_own_word
    @world.callback("+34600", at: "2026-10-08T10:00", note: "after ten")

    assert_equal ["call.callback", { number: "+34600", when: "2026-10-08T10:00", note: "after ten" }], @sent.first
  end

  def test_the_call_ending_answers_every_verb_still_waiting
    answered_by("call.ended", { reason: "caller_hung_up", ended_by: "caller", ended_at: 1.0, duration_s: 1.0 })

    transferred = @world.transfer("+34910")

    refute transferred.ok
    assert_equal Pinecall::CallWorld::THE_CALL_ENDED, transferred.error
  end

  def test_a_search_with_no_gateway_says_so
    error = assert_raises(Pinecall::Error) { @world.search("horario") }
    assert_equal Pinecall::CallWorld::NO_GATEWAY_TO_SEARCH, error.message
  end

  def test_a_search_goes_through_the_gateway_for_this_call
    asked = []
    @world = world { |query, k| (asked << [query, k]) && [{ path: "horario.md", heading: "Horario", text: "de 9 a 18" }] }

    found = @world.search("horario", k: 2)

    assert_equal [["horario", 2]], asked
    assert_equal "de 9 a 18", found.first.text
  end

  def test_today_is_the_day_the_call_opened
    assert_equal "2026-10-07", @world.today
  end

  def test_a_caller_who_asks_never_to_be_called_again_goes_on_the_do_not_call_list_with_the_note
    @world.opt_out("pidió no volver a recibir llamadas")
    @world.opt_out

    assert_equal [["call.opt_out", { note: "pidió no volver a recibir llamadas" }], ["call.opt_out", {}]], @sent
  end

  private

  def stub_const(name, value)
    was = Pinecall::CallWorld.const_get(name)
    Pinecall::CallWorld.send(:remove_const, name)
    Pinecall::CallWorld.const_set(name, value)
    yield
  ensure
    Pinecall::CallWorld.send(:remove_const, name)
    Pinecall::CallWorld.const_set(name, was)
  end
end
