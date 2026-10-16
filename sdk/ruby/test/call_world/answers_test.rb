# frozen_string_literal: true

require "test_helper"

# A verb that waits for an entry: answered by it, lapsed at its ceiling, or ended with the call.
class AnswersTest < Minitest::Test
  Waiting = Pinecall::CallWorld::Waiting

  def test_one_answer_settles_every_verb_of_its_kind
    waiting = Waiting.new
    answers = Array.new(2) { Thread.new { waiting.wait(:spoken, 2, false) { nil } } }
    sleep(0.02)

    waiting.settle(:spoken, true)

    assert_equal [true, true], answers.map(&:value)
  end

  def test_a_verb_nobody_answers_is_lapsed_at_its_ceiling
    assert_equal :lapsed, Waiting.new.wait(:asks, 0.01, :lapsed) { nil }
  end

  def test_the_call_ending_answers_each_kind_with_its_own_sentence
    waiting = Waiting.new
    transfer = Thread.new { waiting.wait(:transfers, 2, nil) { nil } }
    sleep(0.02)

    waiting.end_all

    assert_equal Pinecall::CallWorld::THE_CALL_ENDED, transfer.value.error
  end
end
