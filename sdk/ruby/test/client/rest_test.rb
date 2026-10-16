# frozen_string_literal: true

require "test_helper"
require_relative "rest_gateway"

# A search for a call this client serves: the gateway's lookup door, and the chunks it answered.
class RestTest < Minitest::Test
  def test_a_search_asks_the_lookup_door_of_the_call_and_answers_its_chunks
    chunk = { path: "horario.md", heading: "Horario", text: "de 9 a 18" }
    gateway = RestGateway.new("POST /v1/calls/CA_1/lookup" => [200, { output: { chunks: [chunk] } }])
    client = Pinecall::Client.new(url: gateway.url, api_key: "pk_test")

    found = client.search("CA_1", "cuándo abren", k: 2)

    assert_equal [chunk], found
    assert_equal({ tool: "search", input: { query: "cuándo abren", k: 2 } }, gateway.asked.first.body)
  ensure
    gateway&.stop
  end
end
