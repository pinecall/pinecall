# frozen_string_literal: true

# Ring 0: the class as software — no network, no key, no model.

require "minitest/autorun"
require "pinecall"
require "pinecall/testing"
require_relative "../agent"

class {{Class}}Test < Minitest::Test
  def setup
    @agent = {{Class}}.new.seal
    @agent.serving(Pinecall::CallWorld.new(id: "CA_1", contact: "+15550100", channel: "phone") { |*| nil })
  end

  def view = Pinecall.render(@agent, line: { channel: "phone" })[:view]

  def test_until_there_is_a_message_the_view_asks_for_one
    assert_includes view, "ask only for what the caller has not said yet"
  end

  def test_nothing_is_written_down_on_a_blank_or_a_guess
    error = assert_raises(ArgumentError) { @agent.run_tool("take_message", { name: "Ana", about: "not specified" }) }

    assert_includes error.message, "Nothing was written down"
    assert_equal :ask, @agent.stage
  end

  def test_a_message_taken_ends_the_call_with_it
    @agent.run_tool("take_message", { name: "Ana", about: "a refund" })

    assert_equal :done, @agent.stage
    assert_includes view, "Ana, about a refund"
  end
end
