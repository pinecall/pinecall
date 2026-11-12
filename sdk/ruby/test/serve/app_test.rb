# frozen_string_literal: true

require "test_helper"
require "fileutils"
require "tmpdir"

# The project's voice app in its serve entry: loaded after its agents, whose classes it names, and told.
class ServeAppTest < Minitest::Test
  AGENT = <<~RUBY
    # You answer the clinic's phone.
    class AppTestFrontDesk < Pinecall::Agent; end
  RUBY

  APP = <<~RUBY
    APP = Pinecall.voice_app("brightside").line("+14155550134", AppTestFrontDesk).page("ui/dist")
  RUBY

  def project(root, app = APP)
    folder = File.join(root, "agents", "front-desk")
    FileUtils.mkdir_p(folder)
    File.write(File.join(folder, "agent.rb"), AGENT)
    File.write(File.join(root, "app.rb"), app)
    Pinecall::Serve::Loading.parse(["--file", File.join(folder, "agent.rb"), "--slug", "front-desk", "--app", File.join(root, "app.rb")])
  end

  def test_the_app_names_its_agents_as_they_were_loaded_and_is_told_with_its_page
    Dir.mktmpdir do |root|
      out = StringIO.new

      assert_equal 0, Pinecall::Serve::App.described(project(root), out)
      assert_equal({ name: "brightside", page: { dir: "ui/dist", agent: "front-desk" } }, JSON.parse(out.string, symbolize_names: true))
    end
  end

  def test_a_file_that_makes_no_voice_app_is_refused
    Dir.mktmpdir do |root|
      File.write(File.join(root, "empty.rb"), "VALUE = 1\n")

      assert_raises(Pinecall::Serve::CannotServe) { Pinecall::Serve::App.load_app(File.join(root, "empty.rb")) }
    end
  end
end
