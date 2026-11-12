# frozen_string_literal: true

require "test_helper"

# A tool that stops to ask: answered with the question, and finished once the answer is given.
class AskingTest < Minitest::Test
  def test_a_tool_stops_at_its_question_and_finishes_with_the_answer
    asking = Pinecall::Asking.new([Pinecall::GetEmail])
    first = asking.run("book") { { booked_for: asking.ask(Pinecall::GetEmail) } }

    assert first.end_with?("Then call give_email.")
    assert_equal "give_email", asking.open[:name]
    ended = asking.given("give_email", { email: "Ana@Example.com" })

    assert_equal({ finished: "book", result: { booked_for: "ana@example.com" } }, ended)
    assert_nil asking.open
  end

  def test_an_answer_the_check_refuses_is_said_and_the_question_stays_open
    asking = Pinecall::Asking.new([Pinecall::GetEmail])
    asking.run("book") { asking.ask(Pinecall::GetEmail) }

    assert_raises(Pinecall::ToolFailed) { asking.given("give_email", { email: "ana at example" }) }
    assert_equal "email", asking.asking.task
    assert_raises(Pinecall::ToolFailed) { asking.given("give_email", {}) }
  end

  def test_a_question_outside_a_tool_or_of_another_task_is_refused
    asking = Pinecall::Asking.new([Pinecall::GetEmail])

    assert_raises(Pinecall::Error) { asking.ask(Pinecall::GetEmail) }
    assert_raises(Pinecall::Error) { asking.run("book") { asking.ask(Pinecall::GetPhone) } }
  end

  def test_the_page_may_give_the_answer_and_the_model_is_told_how_it_ended
    asking = Pinecall::Asking.new([Pinecall::GetEmail])
    asking.run("book") { { for: asking.ask(Pinecall::GetEmail) } }

    assert_nil asking.given_by_page("phone", { number: "1" })
    assert_includes asking.given_by_page("email", { email: "ana@example.com" }), "book is done with this result"
  end

  def test_a_call_that_ends_with_a_question_open_tells_the_tool
    asking = Pinecall::Asking.new([Pinecall::GetEmail])
    failed = Thread::Queue.new
    asking.run("book") do
      asking.ask(Pinecall::GetEmail)
    rescue Pinecall::Error => e
      failed.push(e.message)
      raise
    end
    asking.abandon

    assert_equal "the call ended before the caller gave the caller's email address", failed.pop
  end
end
