# frozen_string_literal: true

# Who is in the call's room and what was said: the participants, a seat's two verbs, the turns.

module Pinecall
  # A room participant, as reported by the room's entries.
  Participant = Struct.new(:identity, :kind, :name, :joined_at, :speaking, keyword_init: true)

  # A finished conversation turn.
  Turn = Data.define(:who, :text, :speech_id, :interrupted, :at)

  class CallWorld
    # A participant handle. Removing the caller ends the call.
    class Seat
      def initialize(identity, send)
        @identity = identity
        @send = send
      end

      # For the rest of the call: the wire has no unmute (`participant.mute` carries the identity alone).
      def mute = @send.call("participant.mute", { identity: @identity })

      def remove = @send.call("participant.remove", { identity: @identity })
    end
  end
end
