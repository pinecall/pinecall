# frozen_string_literal: true

require "test_helper"
require "tmpdir"

# The app's page on this machine: its files, its config, and the visitor's ticket passed on.
class PagedTest < Minitest::Test
  def paged(folder) = Pinecall::Serve::Paged.new(folder:, agent: "front-desk", url: "http://127.0.0.1:9", api_key: "pk_test", env: nil, port: 0)

  def test_a_path_that_names_no_file_is_the_page_itself_and_a_missing_file_is_said
    Dir.mktmpdir do |folder|
      File.write(File.join(folder, "index.html"), "<p>page</p>")
      File.write(File.join(folder, "app.js"), "go()")

      assert_equal "<p>page</p>", paged(folder).file_of("/agenda/lunes").body
      assert_equal ["go()", "text/javascript"], paged(folder).file_of("/app.js").then { |said| [said.body, said.type] }
      assert_equal 404, paged(folder).file_of("/missing.css").status
      assert_equal 404, paged(folder).file_of("/../secret").status
    end
  end

  def test_a_dictation_is_answered_with_the_gateways_socket_whole_and_a_refusal_as_it_came
    Dir.mktmpdir do |folder|
      said = Pinecall::Serve::Paged::Said
      minted = said.new(200, '{"token":"t","path":"/v1/transcriptions/stream?token=t"}', "application/json")
      page = Pinecall::Serve::Paged.new(folder:, agent: "front-desk", url: "https://cloud.example/", api_key: "pk_test", env: nil, port: 0)

      assert_equal({ "url" => "wss://cloud.example/v1/transcriptions/stream?token=t", "hear" => [] }, JSON.parse(page.dictating(minted).body))
      refused = said.new(429, '{"detail":"too many dictations this minute"}', "application/json")
      assert_same refused, page.dictating(refused)
      assert_equal 502, page.dictating(said.new(200, "{}", "application/json")).status
    end
  end

  def test_a_page_not_built_yet_says_so_and_the_config_names_the_agent
    Dir.mktmpdir do |folder|
      assert_equal Pinecall::Serve::Paged::NOT_BUILT, JSON.parse(paged(folder).file_of("/").body)["detail"]
      assert_equal({ "agent" => "front-desk", "turnstile" => nil }, JSON.parse(paged(folder).got("/pinecall/config").body))
      assert_equal 405, paged(folder).posted("/elsewhere", "{}").status
    end
  end
end
