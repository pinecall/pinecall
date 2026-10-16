# frozen_string_literal: true

require "test_helper"

# Who is in the room, as its entries say, and a seat's two verbs.
class RoomTest < Minitest::Test
  def setup
    @sent = []
    @world = Pinecall::CallWorld.new(id: "CA_1") { |type, data| @sent << [type, data] }
  end

  def test_a_participant_joins_speaks_and_leaves_as_the_entries_say
    @world.take("participant.joined", { identity: "sip_1", kind: "caller", name: "Ana" }, 1.0)
    @world.take("participant.speaking", { identity: "sip_1", speaking: true }, 2.0)

    assert @world.caller_seat.speaking
    @world.take("participant.left", { identity: "sip_1" }, 3.0)
    assert_empty @world.participants
  end

  def test_a_seat_mutes_and_removes_by_its_identity
    seat = @world.participant("sip_1")
    seat.mute
    seat.remove

    assert_equal [["participant.mute", { identity: "sip_1", muted: true }], ["participant.remove", { identity: "sip_1" }]], @sent
  end
end
