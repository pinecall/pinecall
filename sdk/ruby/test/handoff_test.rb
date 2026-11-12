# frozen_string_literal: true

require "test_helper"

# A team: the tools that offer the call to a teammate, and who answers a line that chooses.
class HandoffTest < Minitest::Test
  # You answer the clinic's phone.
  class FrontDesk < Pinecall::Agent
    # Books a visit.
    tool
    def book(day:) = day
  end

  # You answer questions about bills.
  class BillingDesk < Pinecall::Agent
    takes "questions about a bill"

    # Finds a bill.
    tool
    def find_bill(number:) = number
  end

  TEAM = { FrontDesk => "front-desk", BillingDesk => "billing" }.freeze

  def test_a_call_is_offered_to_each_teammate_that_takes_something_by_its_class
    offered = Pinecall::Handoff.transfers_of(FrontDesk, TEAM)

    assert_equal ["transfer_to_billing_desk"], offered.map { |spec| spec[:name] }
    assert_includes offered.first[:description], "questions about a bill"
    assert_empty Pinecall::Handoff.transfers_of(BillingDesk, TEAM)
    assert_equal BillingDesk, Pinecall::Handoff.mate_named("transfer_to_billing_desk", TEAM)
  end

  def test_a_team_declares_every_tool_once
    assert_equal %w[book transfer_to_billing_desk find_bill], Pinecall::Handoff.team_tools(TEAM).map { |spec| spec[:name] }
  end

  def test_a_line_that_chooses_is_answered_by_its_choice_or_the_bound_agent_and_why
    line = Object.new

    assert_equal BillingDesk, Pinecall::Handoff.answered_by(->(_) { BillingDesk }, line, FrontDesk, TEAM).agent
    assert_equal "answers raised: no CRM", Pinecall::Handoff.answered_by(->(_) { raise "no CRM" }, line, FrontDesk, TEAM).why
    late = Pinecall::Handoff.answered_by(->(_) { sleep(2) }, line, FrontDesk, TEAM)

    assert_equal FrontDesk, late.agent
    assert_includes late.why, "took more than"
  end
end
