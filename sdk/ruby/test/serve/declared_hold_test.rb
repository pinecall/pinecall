# frozen_string_literal: true

require "test_helper"
require "tmpdir"

# A class that declares its hold melody names the file by its hash and ships it once registered.
class DeclaredHoldTest < Minitest::Test
  DeclaredHold = Pinecall::Serve::DeclaredHold
  MELODY = "RIFF\x01\x02\x03\x04".b
  SHA = Digest::SHA256.hexdigest(MELODY)

  # Plays its own file after a second and a half.
  class Plays < Pinecall::Agent
    hold file: "hold.mp3", after_s: 1.5
  end

  # Plays nothing.
  class Quiet < Pinecall::Agent
    hold :off
  end

  def beside
    dir = Dir.mktmpdir("declared-hold")
    File.binwrite(File.join(dir, "hold.mp3"), MELODY)
    File.join(dir, "agent.rb")
  end

  def client = Pinecall::Client.new(url: "https://gw", api_key: "pk_test")

  def test_the_file_is_declared_by_its_hash_with_the_wait_and_silence_as_off
    assert_equal({ after_s: 1.5, clip: SHA, name: "hold.mp3" }, Pinecall::Agent::Melody.config_of(Plays.hold, beside))
    assert_equal({ off: true }, Quiet.wire_config(tools: [])[:hold])
    refute Pinecall::Agent.wire_config(tools: []).key?(:hold)
    error = assert_raises(Pinecall::DeclarationRefused) { Pinecall::Agent::Melody.config_of({ file: "nowhere.mp3" }, beside) }
    assert_includes error.message, "no such file beside the class"
  end

  def test_the_file_is_shipped_once_registered_and_not_again_when_the_gateway_holds_it
    file = beside
    held = { played: "default", after_s: 2.5, source_sha256: nil }
    shipped = []
    get = ->(_url, api_key:, env:) { held }
    put = lambda do |url, bytes, api_key:, env:|
      shipped << [url, bytes]
      { played: "custom", seconds: 41.2, source_sha256: SHA }
    end
    err = StringIO.new
    DeclaredHold.upload(client, Plays, file, err:, get:, put:)

    assert_equal [["https://gw/v1/agents/plays/hold-audio?name=hold.mp3", MELODY]], shipped
    assert_equal "plays  hold.mp3 uploaded as the hold melody · 41.2 s\n", err.string
    held[:source_sha256] = SHA
    DeclaredHold.upload(client, Plays, file, err:, get:, put:)

    assert_equal 1, shipped.size
    DeclaredHold.upload(client, Quiet, file, err:, get:, put:)

    assert_equal 1, shipped.size
  end
end
