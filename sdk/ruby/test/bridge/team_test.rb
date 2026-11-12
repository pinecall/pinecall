# frozen_string_literal: true

require "test_helper"

# A tool call on a served call: a teammate takes it, a task is asked and given, a scene shown.
class TeamTest < Minitest::Test
  Agenda = Pinecall.part("agenda")

  # You answer the clinic's phone.
  class FrontDesk < Pinecall::Agent
    tasks Pinecall::GetEmail
    scenes agenda: "the open times"

    # Reads the open times of a day.
    tool shows: :agenda
    def look(day:) = ["#{day} 9:00"]

    # Books a visit, asking where to send it.
    tool
    def book(day:) = { day:, email: ask(Pinecall::GetEmail) }

    def screen = Agenda.(open: call.scene == "agenda")
  end

  # You answer questions about bills.
  class Billing < Pinecall::Agent
    takes "questions about a bill"

    # Finds a bill.
    tool
    def find_bill(number:) = number
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    @mounted = Pinecall.mount(FrontDesk, client: @gateway, slug: "front-desk", team: { FrontDesk => "front-desk", Billing => "billing" })
    @call = @gateway.call_started
  end

  def test_a_teammate_takes_the_call_with_its_own_tools_and_the_pass_on_the_log
    said = @call.tool("transfer_to_billing", reason: "a bill")

    assert_equal "The call is billing's now: go on as billing, without saying it was passed.", said[:output]
    assert_instance_of Billing, @mounted.serving(@call.id)
    logged = @call.commands.select { |sent| sent.type == "call.log" && sent.data[:name] == "handoff" }

    assert_equal({ from: "front-desk", to: "billing", reason: "a bill" }, logged.first.data[:data])
    assert_equal ["find_bill"], @call.tools
  end

  def test_a_tool_that_asks_leaves_one_tool_open_and_finishes_once_it_is_given
    asked = @call.tool("book", day: "lunes")

    assert asked[:output].end_with?("Then call give_email.")
    assert_equal ["give_email"], @call.tools
    ended = @call.tool("give_email", email: "Ana@Example.com")

    assert_equal({ finished: "book", result: { day: "lunes", email: "ana@example.com" } }, ended[:output])
  end

  def test_a_tool_that_shows_a_scene_puts_it_up_on_the_screen_the_state_carries
    @call.tool("look", day: "lunes")

    assert_equal [{ part: "agenda", props: { open: true }, children: [] }], @call.state[:screen]
    assert_equal "shown", @call.tool("show_screen", scene: "none")[:output]
  end
end
