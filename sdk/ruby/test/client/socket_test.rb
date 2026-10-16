# frozen_string_literal: true

require "test_helper"
require_relative "fake_gateway"

# The client socket against a real TCP/WebSocket server: auth, register/configure, commands.
class SocketTest < Minitest::Test
  def setup
    @gateway = FakeGateway.new
    @client = Pinecall::Client.new(url: @gateway.url, api_key: "pk_test_key")
  end

  def teardown
    @client.close
    @gateway.stop
  end

  def test_it_registers_every_agent_it_holds_the_moment_the_socket_opens
    @client.agent("clinica-norte", routes: [{ channel: "web", number: nil }], tools: [])
    @client.connect

    assert_predicate @client, :connected?
    registered = @gateway.frames.pop(timeout: 5)

    assert_equal "agent.register", registered[:type]
    assert_equal "clinica-norte", registered[:agent]
    assert_match(%r{\Apinecall-ruby/}, registered[:data][:sdk])
  end

  def test_the_key_travels_in_a_header_and_never_in_the_url
    @client.agent("clinica-norte", tools: [])
    @client.connect
    @gateway.frames.pop(timeout: 5)

    assert_equal "Bearer pk_test_key", @gateway.authorization
  end

  def test_the_declaration_follows_the_registration_without_being_asked
    @client.agent("clinica-norte", tools: [], uses_knowledge: true)
    @client.connect
    @gateway.frames.pop(timeout: 5)
    configured = @gateway.frames.pop(timeout: 5)

    assert_equal "agent.configure", configured[:type]
    assert_equal true, configured[:data][:config][:uses_knowledge]
  end

  def test_a_command_the_wire_refuses_never_reaches_the_socket
    agent = @client.agent("clinica-norte", tools: [])
    @client.connect
    @gateway.frames.pop(timeout: 5)

    assert_raises(Pinecall::Wire::WireError) { agent.command("agent.say", "CA_1", { shout: true }) }
  end

  def test_a_command_goes_up_as_the_wire_carries_it
    agent = @client.agent("clinica-norte", tools: [])
    @client.connect
    2.times { @gateway.frames.pop(timeout: 5) }
    agent.command("agent.say", "CA_1", { text: "Buenas tardes." })
    said = @gateway.frames.pop(timeout: 5)

    assert_equal "agent.say", said[:type]
    assert_equal "CA_1", said[:call]
    assert_equal "Buenas tardes.", said[:data][:text]
  end

  def test_a_command_sent_while_the_socket_is_down_is_refused_and_not_queued
    agent = @client.agent("clinica-norte", tools: [])

    assert_raises(Pinecall::NotConnected) { agent.command("ping", nil, {}) }
  end

  def test_a_client_with_no_url_and_no_key_says_which_two_things_it_needs
    refused = assert_raises(ArgumentError) { Pinecall::Client.new(url: nil, api_key: nil) }

    assert_includes refused.message, "url:, api_key:"
  end
end
