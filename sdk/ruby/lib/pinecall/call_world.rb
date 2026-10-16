# frozen_string_literal: true

require_relative "call_world/room"
require_relative "call_world/answers"

module Pinecall
  # The call as an agent sees it: room, turns, and the commands it can send.
  #
  # State is reduced from received entries; each verb is one wire command. No LiveKit access by
  # design: a missing capability should become a new command of the wire.
  class CallWorld
    attr_reader :id, :contact, :from, :channel, :medium, :room, :turns, :today, :claimed

    # `send` puts one command on the wire for this call; `searching` asks the gateway to search for
    # it. Both are supplied by the bridge. `today` is the day the call opened, YYYY-MM-DD. `medium` is
    # spoken (`voice`) or written (`text`); a gateway that does not say gets it from the channel.
    def initialize(id:, contact: nil, from: nil, channel: nil, medium: nil, today: Time.now.strftime("%Y-%m-%d"),
                   claimed: nil, searching: nil, &send)
      @id = id
      @contact = contact
      @from = from
      @channel = channel
      @medium = (medium || (channel.to_s == "whatsapp" ? "text" : "voice")).to_s
      @today = today
      @claimed = claimed
      @searching = searching
      @send = send
      @room = { participants: [], caller: nil }
      @turns = []
      @waiting = Waiting.new
      @cause = nil
      @events = 0
    end

    # The external event being handled, if any; logged as the cause of state changes.
    attr_accessor :cause

    # Next per-call event sequence number (not the wire's seq).
    def numbered = @events += 1

    # ── commands ─────────────────────────────────────────────────────────────

    # Speak `text` verbatim now. Returns true once the turn arrives, false after `LANDS_WITHIN_S`.
    def say(text, **options)
      @waiting.wait(:spoken, LANDS_WITHIN_S, false) { @send.call("agent.say", { text: }.merge(options)) }
    end

    # Make the model speak now, guided by instructions the caller does not hear.
    def reply(instructions, **options)
      @waiting.wait(:spoken, LANDS_WITHIN_S, false) { @send.call("agent.reply", { instructions: }.merge(options)) }
    end

    # Search the knowledge bases attached to this agent; the gateway runs it and logs the results.
    # `k` defaults to each base's own setting.
    def search(query, k: nil)
      raise Error, NO_GATEWAY_TO_SEARCH if @searching.nil?

      @searching.call(query, k).map { |chunk| Found.new(path: chunk[:path], heading: chunk[:heading], text: chunk[:text]) }
    end

    # Transfer the caller to a number: sent on (cold) on a phone call, dialled into the call (warm)
    # in a browser; `mode:` forces one. `ok: false` means the caller is still with the agent.
    def transfer(to, mode: nil)
      wanted = mode.nil? ? { to: } : { to:, mode: mode.to_s }
      lapsed = Transferred.new(to:, mode: nil, ok: false, error: NO_ANSWER)
      @waiting.wait(:transfers, TRANSFER_WITHIN_S, lapsed) { @send.call("call.transfer", wanted) }
    end

    # Ask for a supervisor; the caller waits until someone takes the line or `wait_s` passes.
    # `reason` is shown to the supervisor. The calling tool runs the whole time.
    def attention(reason, wait_s:)
      lapsed = Attended.new(ok: false, by: nil, error: NO_ANSWER)
      @waiting.wait(:asks, wait_s + A_MOMENT_S, lapsed) { @send.call("call.attention", { reason:, wait_s: }) }
    end

    # Put the caller on hold: they hear hold music and the agent neither speaks nor listens.
    def hold = @send.call("call.hold", {})

    # Take the caller off hold.
    def unhold = @send.call("call.unhold", {})

    # Send DTMF tones: `0-9`, `*`, `#`, and `,` for a pause.
    def dtmf(digits) = @send.call("call.dtmf", { digits: })

    # Bind this call to the four-digit code shown on the caller's page; `claimed` is set when the
    # log says it took. A code that is not four digits never reaches the wire.
    def claim(code) = @send.call("call.claim", { code: })

    # Record a callback request in the call's log for the backend to dial. `at:` is the wire's `when`.
    def callback(number, at: nil, note: nil)
      @send.call("call.callback", { number:, when: at, note: }.compact)
    end

    # Send a payload to browsers in the room. The log records its size, not its content.
    def send_to(topic, data, to: nil)
      payload = { topic:, data: }
      payload[:to] = Array(to) unless to.nil?
      @send.call("room.send", payload)
    end

    # A participant handle by identity.
    def participant(identity) = Seat.new(identity, @send)

    # Invite a second SIP leg or a person.
    def invite(to, kind: nil)
      wanted = { to: }
      wanted[:kind] = kind.to_s unless kind.nil?
      @send.call("room.invite", wanted)
    end

    # Append an application entry to the call's log.
    def log(name, data = {})
      @send.call("call.log", { name: name.to_s, data: data.is_a?(Hash) ? data : { value: data } })
    end

    # The caller asked never to be called again: their number joins the org's do-not-call list, and no
    # call of the org reaches it until a consent is recorded. Tell them it is done.
    def opt_out(note = nil)
      @send.call("call.opt_out", note.nil? ? {} : { note: })
    end

    # End the call; `call.ended` follows with reason `agent_hung_up`.
    def hangup(reason = nil)
      @send.call("call.hangup", reason.nil? ? {} : { reason: })
    end

    # ── entries ──────────────────────────────────────────────────────────────

    # Apply one log entry to the room, the turns and the verbs waiting on it.
    def take(type, data, at)
      case type
      when "participant.joined" then joined(data, at)
      when "participant.left" then @room[:participants].reject! { |one| one.identity == data[:identity] }
      when "participant.speaking" then speaking(data)
      when "turn.user" then remember("user", data, at)
      when "turn.agent" then remember("agent", data, at).tap { @waiting.settle(:spoken, true) }
      when "call.claimed" then @claimed = data[:code].to_s
      when "call.transferred" then @waiting.settle(:transfers, transferred(data))
      when "attention.answered" then @waiting.settle(:asks, Attended.new(ok: data[:ok] == true, by: data[:by], error: data[:error]))
      when "call.ended" then @waiting.end_all
      end
    end

    def participants = @room[:participants].dup

    # The caller's participant, or nil.
    def caller_seat = @room[:participants].find { |one| one.kind == "caller" }

    def last_turn = @turns.last

    private

    def joined(data, at)
      @room[:participants] << Participant.new(
        identity: data[:identity], kind: data[:kind], name: data[:name], joined_at: at, speaking: false
      )
    end

    def speaking(data)
      who = @room[:participants].find { |one| one.identity == data[:identity] }
      who.speaking = data[:speaking] unless who.nil?
    end

    def remember(who, data, at)
      turn = Turn.new(who:, text: data[:text], speech_id: data[:speech_id],
                      interrupted: data[:interrupted] || false, at:)
      @turns << turn
      turn
    end

    def transferred(data)
      Transferred.new(to: data[:to].to_s, mode: data[:mode], ok: data[:ok] == true, error: data[:error])
    end
  end
end
