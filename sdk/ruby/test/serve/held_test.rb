# frozen_string_literal: true

require "test_helper"
require_relative "../client/fake_gateway"

# What a process holds and how it leaves: `Pinecall.serve`'s `stop` drains, closes and says where the calls went.
class HeldTest < Minitest::Test
  # Atiende en la clínica.
  class Clinica < Pinecall::Agent
  end

  def setup = @gateway = FakeGateway.new

  def teardown = @gateway.stop

  def serve = Pinecall.serve(Clinica, url: @gateway.url, api_key: "pk_test", slug: "clinica")

  def test_stopping_what_pinecall_serve_holds_says_on_stderr_where_the_calls_went
    _out, said = capture_io { serve.stop }

    refute_nil @gateway.next_frame("agent.drain")
    assert_equal "draining · no live calls\n", said
  end

  def test_asked_twice_it_drains_and_says_it_once
    _out, said = capture_io do
      held = serve
      held.stop
      held.stop
    end

    assert_equal "draining · no live calls\n", said
  end

  def test_the_line_goes_where_the_holder_was_told_to_write
    err = StringIO.new
    held = Pinecall::Serve::Held.new(serve.client, [], err:)
    held.stop

    assert_equal "draining · no live calls\n", err.string
  end
end
