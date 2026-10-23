# frozen_string_literal: true

require "pp"
require "test_helper"
require_relative "fake_gateway"

# No object the SDK builds prints the API key: a log line, an exception or `p` shows what `inspect` says.
class InspectTest < Minitest::Test
  KEY = "pc_live_k3y0f1ndm3if4nyb0dyp1nt5it"

  # Atiende la clínica.
  class Clinica < Pinecall::Agent
    # Mira la agenda.
    tool
    def look = "ok"
  end

  def setup = @gateway = FakeGateway.new

  def teardown
    @held&.close
    @gateway.stop
  end

  def until_a_call_is_live(agent)
    deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 5
    sleep(0.02) until agent.calls.live.any? || Process.clock_gettime(Process::CLOCK_MONOTONIC) > deadline
  end

  def test_nothing_the_sdk_builds_prints_the_key
    @held = Pinecall.serve(Clinica, url: @gateway.url, api_key: KEY, env: "production", slug: "clinica")
    started = { channel: "web", direction: "inbound", from: "+34600", to: "+34910", caller: nil, started_at: Time.now.to_f }
    @gateway.send_entry("clinica", "call.started", started, call: "CA_1")
    agent = @held.client.agents.fetch("clinica")
    until_a_call_is_live(agent)
    refute_nil @gateway.next_frame("tools.set"), "the call was never served"
    objects = [@held, @held.client, @held.mounted.first, agent, agent.calls, *agent.calls.live,
               @held.client.instance_variable_get(:@connection)]

    refute_empty agent.calls.live
    objects.each do |object|
      [object.inspect, object.to_s, PP.pp(object, +"")].each { |shown| refute_includes shown, KEY, "#{object.class} shows the key" }
    end
  end

  def test_the_client_still_says_where_it_is_and_what_it_holds
    client = Pinecall::Client.new(url: "https://cloud.pinecall.io", api_key: KEY, env: "production")
    client.agent("clinica", tools: [])

    assert_equal '#<Pinecall::Client https://cloud.pinecall.io env="production" agents=["clinica"]>', client.inspect
  end
end
