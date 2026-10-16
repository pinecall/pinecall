# frozen_string_literal: true

require "test_helper"
require_relative "fake_gateway"

# One agent from the app's side, on a real socket: it leaves by draining, and a console's ask is answered.
class AgentTest < Minitest::Test
  def setup
    @gateway = FakeGateway.new
    @client = Pinecall::Client.new(url: @gateway.url, api_key: "pk_test", env: "production")
    @client.on_errors { |_error| nil }
    @client.agent("clinica-norte", tools: [])
    @client.connect
  end

  def teardown
    @client.close
    @gateway.stop
  end

  def test_a_drain_asks_the_gateway_and_says_where_the_calls_went
    drained = @client.drain(tools_s: 0.1)

    refute_nil @gateway.next_frame("agent.drain")
    assert_equal [0, 0, 0, 0], [drained.handed, drained.parked, drained.tools, drained.finished]
  end

  def test_a_socket_that_closed_before_the_drain_was_asked_is_a_drain_with_nothing_to_hand_over
    errors = []
    @client.on_errors { |error| errors << error }
    client = @client
    @client.agents["clinica-norte"].define_singleton_method(:drain) do |**|
      client.close
      raise Pinecall::NotConnected, "agent.drain: the gateway is not connected"
    end
    drained = @client.drain(tools_s: 0.1)

    assert_equal [0, 0], [drained.handed, drained.parked]
    assert_empty errors
  end

  def test_a_consoles_ask_with_nobody_to_answer_it_is_a_501_that_says_so
    @gateway.send_entry("clinica-norte", "dev.request", { id: "dev_1", verb: "view.render", data: {} })

    answer = @gateway.next_frame("dev.answer")
    assert_equal({ id: "dev_1", refused: { status: 501, detail: Pinecall::Client::Agent::NO_DEV_HANDLER } }, answer[:data])
  end

  def test_a_consoles_ask_is_answered_by_the_handler_or_refused_with_its_status
    @client.agents["clinica-norte"].on_dev do |verb, data|
      raise Pinecall::DevRefused.new(404, "no #{verb} here") unless verb == "view.render"

      { name: "Ficha", nodes: [{ tag: "text", text: data[:contact] }] }
    end
    @gateway.send_entry("clinica-norte", "dev.request", { id: "dev_2", verb: "view.render", data: { contact: "+34600", call: "CA_1" } })
    @gateway.send_entry("clinica-norte", "dev.request", { id: "dev_3", verb: "goldens.roster", data: {} })

    answers = [@gateway.next_frame("dev.answer"), @gateway.next_frame("dev.answer")].map { |frame| frame[:data] }
    assert_includes answers, { id: "dev_2", result: { name: "Ficha", nodes: [{ tag: "text", text: "+34600" }] } }
    assert_includes answers, { id: "dev_3", refused: { status: 404, detail: "no goldens.roster here" } }
  end

  def test_connected_is_said_once_every_agent_on_the_socket_registered
    connected = Thread::Queue.new
    client = Pinecall::Client.new(url: @gateway.url, api_key: "pk_test", env: "production")
    client.on_errors { |_error| nil }
    client.agent("tienda-sur", tools: [])
    client.on_connected { connected << client.agents["tienda-sur"].app }
    client.connect

    refute_nil connected.pop(timeout: 5)
  ensure
    client&.close
  end

  def test_the_socket_says_which_world_it_acts_in_and_where_it_runs
    registered = @gateway.next_frame("agent.register")

    assert_equal "production", @gateway.world
    assert_equal Socket.gethostname, registered[:data][:host]
  end

  def test_every_entry_reaches_on_entries_as_the_gateway_wrote_it
    seen = Thread::Queue.new
    @client.on_entries { |entry| seen << entry }
    @gateway.send_entry("tienda-sur", "agent.configured", { changed: %w[tools] })

    entry = seen.pop(timeout: 5)
    assert_equal ["agent.configured", "tienda-sur", { changed: %w[tools] }], [entry.type, entry.agent, entry.data]
  end

  def test_a_vendor_that_switches_mid_call_is_read_and_the_socket_keeps_answering
    errors = Thread::Queue.new
    @client.on_errors { |error| errors << error }
    @gateway.send_entry("clinica-norte", "vendor.switched", { stage: "tts", vendor: "elevenlabs", model: "eleven_flash_v2_5",
                                                              available: false, serving: "cartesia", serving_model: "sonic-2" }, call: "CA_1")
    @gateway.send_entry("clinica-norte", "dev.request", { id: "dev_2", verb: "view.render", data: {} })

    refute_nil @gateway.next_frame("dev.answer")
    assert_nil errors.pop(timeout: 0.2)
  end

  def test_a_stop_from_the_org_is_said_once_and_the_socket_closes_for_good
    why = Thread::Queue.new
    @client.on_stopped { |said| why << said }
    @gateway.send_entry("", "error", { code: "stopped", message: "stopped by Lucía" })

    assert_equal "stopped by Lucía", why.pop(timeout: 5)
    refute @client.connected?
  end
end
