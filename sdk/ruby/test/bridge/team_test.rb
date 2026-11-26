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

  # You book and move visits.
  class Reception < Pinecall::Agent
    takes "anything about a visit"
    state :patient, ""
    state :visits, []

    def on_call(_call)
      self.patient = "nobody yet"
      self.visits = []
    end

    # How many visits the caller has on the books.
    tool
    def on_the_books = visits.length
  end

  # You answer questions about invoices.
  class Bills < Pinecall::Agent
    takes "questions about an invoice"
    state :invoice, ""
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    @mounted = Pinecall.mount(FrontDesk, client: @gateway, slug: "front-desk", team: { FrontDesk => "front-desk", Billing => "billing" })
    @call = @gateway.call_started
  end

  def test_a_teammate_takes_the_call_with_its_own_tools_and_the_pass_on_the_log
    said = @call.tool("transfer_to_billing", reason: "a bill")

    assert_equal "Done: you are billing now, and the caller is already talking to you. There is nobody left to connect " \
                 'them to, so never say "one moment" or that you are connecting or transferring them. ' \
                 "Reply to their last message now, as billing.", said[:output]
    assert_instance_of Billing, @mounted.serving(@call.id)
    logged = @call.commands.select { |sent| sent.type == "call.log" && sent.data[:name] == "handoff" }

    assert_equal({ from: "front-desk", to: "billing", reason: "a bill" }, logged.first.data[:data])
    assert_equal ["find_bill"], @call.tools
  end

  # 2026-11-25: two simulated calls passed to billing and back found, on their return, a reception with none
  # of the visits their caller was seeded with: the state was laid over the first instance alone.
  def test_a_call_that_opened_in_a_state_is_served_from_it_by_every_agent_that_takes_it
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Reception, client: gateway, slug: "reception", team: { Reception => "reception", Bills => "bills" })
    call = gateway.call_started(state: { patient: "Tom Baker", visits: ["v-207"], invoice: "inv_9" })

    assert_equal({ patient: "Tom Baker", visits: ["v-207"] }, call.state)
    call.tool("transfer_to_bills")

    assert_equal({ invoice: "inv_9" }, call.state)
    call.tool("transfer_to_reception")

    assert_equal({ patient: "Tom Baker", visits: ["v-207"] }, call.state)
    assert_equal 1, call.tool("on_the_books")[:output]
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
