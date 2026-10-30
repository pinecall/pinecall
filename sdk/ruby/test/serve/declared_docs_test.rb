# frozen_string_literal: true

require "test_helper"
require "tmpdir"

# A class that declares `docs` pushes the folder beside it once registered: every Markdown file, by path.
class DeclaredDocsTest < Minitest::Test
  DeclaredDocs = Pinecall::Serve::DeclaredDocs

  # Reads its base per turn, and owns the folder beside it.
  class Reads < Pinecall::Agent
    docs base: "front-desk", k: 4
  end

  # Declares no base.
  class Silent < Pinecall::Agent
  end

  def folder(files)
    dir = Dir.mktmpdir("declared-docs")
    files.each do |path, text|
      FileUtils.mkdir_p(File.dirname(File.join(dir, path)))
      File.write(File.join(dir, path), text)
    end
    dir
  end

  def client = Pinecall::Client.new(url: "https://gw", api_key: "pk_test")

  def test_every_markdown_file_under_the_folder_is_read_by_its_path_and_nothing_for_no_folder
    dir = folder("docs/hours.md" => "# Hours", "docs/policies/insurance.md" => "# Insurance", "docs/notes.txt" => "no")

    assert_equal [{ path: "hours.md", text: "# Hours" }, { path: "policies/insurance.md", text: "# Insurance" }],
                 DeclaredDocs.markdown_under(File.join(dir, "docs"))
    assert_empty DeclaredDocs.markdown_under(File.join(dir, "nowhere"))
  end

  def test_the_folder_beside_a_class_that_declares_docs_is_pushed_and_said
    dir = folder("docs/hours.md" => "# Hours")
    pushed = []
    put = lambda do |url, body, api_key:, env:|
      pushed << [url, body, api_key, env]
      { base: "front-desk", chunks: 7, kept: 2, language: "es", took_ms: 1.0 }
    end
    err = StringIO.new
    DeclaredDocs.push(client, Reads, File.join(dir, "agent.rb"), err:, put:)

    assert_equal [["https://gw/v1/knowledge/front-desk", { files: [{ path: "hours.md", text: "# Hours" }] }, "pk_test", nil]], pushed
    assert_equal "reads  front-desk  1 file(s) pushed · 7 chunk(s) · 2 kept\n", err.string
  end

  def test_nothing_is_pushed_for_a_class_with_no_base_or_a_folder_that_is_not_there
    dir = folder("docs/hours.md" => "# Hours")
    put = ->(*) { raise "nothing should be pushed" }
    err = StringIO.new
    DeclaredDocs.push(client, Silent, File.join(dir, "agent.rb"), err:, put:)
    DeclaredDocs.push(client, Reads, File.join(folder({}), "agent.rb"), err:, put:)

    assert_empty err.string
  end
end
