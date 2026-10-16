# frozen_string_literal: true

# Folds a log into its State, entry by entry, as the runtime's reducer does.

module Pinecall
  module Wire
    # Folds a log into its State, entry by entry. Must match the TypeScript and Python reducers;
    # the golden fixture checks all three.
    module Reduce
      # Error code recorded for an entry the reader cannot decode.
      UNREADABLE = "unreadable"

      module_function

      # Fold every entry, in the order given, into the state an empty log starts from.
      def reduce(entries)
        entries.reduce(State.initial) { |state, entry| apply(state, entry) }
      end

      # Fold one entry in. A gap with a snapshot replaces the state; every other entry mutates it
      # in place. The seq always advances.
      def apply(state, entry)
        event = begin
          Codec.event_of(entry)
        rescue WireError => why
          return moved(unreadable(state, entry, why), entry)
        end
        following = event.type == "log.gap" ? on_log_gap(state, event.data) : apply_event(state, entry, event)
        moved(following, entry)
      end

      # Old logs may hold entries in shapes this reader no longer accepts. Record one error and
      # keep folding instead of rejecting the whole call; the Python and TypeScript reducers agree.
      def unreadable(state, entry, why)
        said = why.message.to_s.lines.first.to_s.strip
        state[:errors] << {
          seq: entry.seq,
          code: UNREADABLE,
          message: "#{entry.type} at seq #{entry.seq} is not the shape this reader knows: #{said}"
        }
        state
      end

      # Advance the fold to the entry's seq, whatever the entry was.
      def moved(state, entry)
        state[:seq] = entry.seq
        state[:agent] = entry.agent
        state[:call] = entry.call unless entry.call.nil?
        state
      end

      # rubocop:disable Metrics/MethodLength, Metrics/CyclomaticComplexity
      def apply_event(state, entry, event)
        data = event.data
        case event.type
        # ── the call ──
        when "call.ringing" then the_line(state, data, status: "ringing", direction: "inbound")
        when "call.dialing" then the_line(state, data, status: "dialing", direction: "outbound")
        when "call.started" then started(state, data)
        when "call.ended" then ended(state, data)
        when "call.transferred" then transferred(state, data)
        when "call.line" then state.merge!(held: data[:held], muted: data[:muted])
        when "call.summary" then summarised(state, data)
        # ── the conversation ──
        when "user.state" then state[:user_state] = data[:state]
        when "agent.state" then state[:agent_state] = data[:state]
        when "user.transcript" then state[:live][:user] = data[:final] ? nil : data[:text]
        when "agent.transcript" then state[:live][:agent] = data[:final] ? nil : said_so_far(state[:live][:agent], data)
        when "turn.user" then turn(state, data, "user")
        when "turn.agent" then turn(state, data, "agent")
        when "memory.ops" then state[:memory].concat(data[:ops])
        when "docs.sources" then state[:sources] = data[:sources].dup
        # ── metrics: every block is kept, in order, by kind ──
        when "metrics.llm", "metrics.stt", "metrics.tts", "metrics.vad", "metrics.eou",
             "metrics.eot", "metrics.interruption", "metrics.realtime", "metrics.avatar"
          state[:metrics][event.type.delete_prefix("metrics.").to_sym] << data
        # ── tools, state, confirmation ──
        when "tool.call" then state[:tools] << data.merge(status: "running", seq: entry.seq)
        when "tool.result" then on_tool_result(state, data)
        when "state.changed" then state[:app_state] = data[:state].dup
        when "prompt.changed" then on_prompt_changed(state, data, entry)
        when "tools.changed" then state[:tools_visible] = data[:visible].dup
        when "confirm.request" then requested(state, data)
        when "confirm.granted" then settle(state, data[:call_id], { status: "granted", said: data[:said] })
        when "confirm.declined" then declined(state, data)
        # ── supervision, the agent, markers ──
        when "supervisor.took_over" then state[:handoff] = { active: true, by: data[:by] }
        when "supervisor.released" then state[:handoff] = { active: false, by: nil }
        when "supervisor.transferred" then took_the_line(state, data)
        when "attention.requested" then asked_for_a_person(state, data, entry.ts)
        when "attention.answered" then answered(state, data)
        when "agent.registered" then state[:routes] = data[:routes].dup
        when "error" then state[:errors] << { seq: entry.seq, code: data[:code], message: data[:message] }
        when "custom" then state[:custom] << { seq: entry.seq, name: data[:name], data: data[:data].dup }
        # ── the room and the outside world ──
        when "room.opened" then state[:room] = { name: data[:name], sid: data[:sid], participants: [], caller: nil }
        when "participant.joined" then joined(state, data, entry.ts)
        when "participant.left" then left(state, data[:identity])
        when "participant.speaking" then speaking(state, data)
        when "event.received" then state[:events] << data.except(:data).merge(seq: entry.seq)
        end
        state
      end
      # rubocop:enable Metrics/MethodLength, Metrics/CyclomaticComplexity

      # Not reduced (the case above leaves the state unchanged): supervisor.said/.whispered surface
      # as turns and prompt changes, supervisor.ended as call.ended; agent.configured, pong,
      # log.caught_up, track.published, track.unpublished and room.sent stay in the log only.

      def the_line(state, line, status:, direction:)
        state.merge!(
          status:,
          direction:,
          channel: line[:channel],
          from: line[:from],
          to: line[:to],
          caller: line[:caller]
        )
      end

      def started(state, data)
        the_line(state, data, status: "active", direction: data[:direction])
        state[:started_at] = data[:started_at]
      end

      def ended(state, data)
        state[:status] = "ended"
        state[:ended_at] = data[:ended_at]
        state[:end_reason] = data[:reason]
        state[:live] = { user: nil, agent: nil }
        # A caller who hung up while waiting for a person was never answered.
        state[:attention] = state[:attention].merge(status: "lapsed") if state[:attention]&.fetch(:status) == "open"
      end

      def transferred(state, data)
        state[:transfer] = {
          to: data[:to],
          mode: data[:mode],
          status: data[:ok] ? "done" : "failed",
          by: state[:transfer]&.fetch(:by, nil) || "agent"
        }
      end

      def took_the_line(state, data)
        state[:transfer] = { to: data[:to], mode: data[:mode], status: "requested", by: "supervisor" }
      end

      def asked_for_a_person(state, data, asked_at)
        state[:attention] = { reason: data[:reason], wait_s: data[:wait_s], status: "open", asked_at: asked_at, by: nil }
      end

      def answered(state, data)
        return if state[:attention].nil?

        state[:attention] = state[:attention].merge(status: data[:ok] ? "answered" : "lapsed", by: data[:by])
      end

      def summarised(state, data)
        state[:usage] = data[:usage].dup
        state[:cost] = data[:cost]
        state[:outcome] = data[:outcome]
        state[:end_reason] ||= data[:reason]
      end

      # A delta: one word of a spoken reply or one token of a written one. Aligned voice words
      # arrive bare and are joined with a space; written tokens carry their own spacing.
      def said_so_far(so_far, data)
        return data[:text] if so_far.nil? || so_far.empty?

        apart = so_far.match?(/\s\z/) || data[:text].match?(/\A\s/)
        !data[:start].nil? && !apart ? "#{so_far} #{data[:text]}" : "#{so_far}#{data[:text]}"
      end

      def turn(state, data, who)
        state[:turns] << { role: who }.merge(data)
        state[:live][who.to_sym] = nil
      end

      def requested(state, data)
        state[:confirms] << {
          tool: data[:tool],
          call_id: data[:call_id],
          audience: data[:audience],
          phrase: data[:phrase],
          status: "pending"
        }
      end

      def declined(state, data)
        verdict = { status: "declined", reason: data[:reason] }
        verdict[:said] = data[:said] if data.key?(:said)
        settle(state, data[:call_id], verdict)
      end

      def on_tool_result(state, result)
        at = state[:tools].rindex { |run| run[:call_id] == result[:call_id] }
        return if at.nil?

        outcome = result.except(:call_id, :name)
        state[:tools][at] = state[:tools][at].merge(outcome, status: outcome.key?(:error) ? "failed" : "done")
      end

      def settle(state, call_id, verdict)
        at = state[:confirms].rindex { |confirm| confirm[:call_id] == call_id }
        return if at.nil?

        state[:confirms][at] = state[:confirms][at].merge(verdict)
      end

      def on_prompt_changed(state, data, entry)
        state[:prompt][data[:name].to_sym] = { hash: data[:hash], chars: data[:chars], seq: entry.seq }
      end

      # joined_at is the entry's ts; the event does not repeat it.
      def joined(state, joined, at)
        return if state[:room].nil?

        state[:room][:participants] << joined.merge(joined_at: at, speaking: false)
        state[:room][:caller] = joined[:identity] if joined[:kind] == "caller"
      end

      # An identity is unique within a room: LiveKit disconnects the first of two that share one.
      def left(state, identity)
        return if state[:room].nil?

        state[:room][:participants].reject! { |one| one[:identity] == identity }
        state[:room][:caller] = nil if state[:room][:caller] == identity
      end

      def speaking(state, data)
        who = state[:room]&.fetch(:participants)&.find { |one| one[:identity] == data[:identity] }
        who[:speaking] = data[:speaking] unless who.nil?
      end

      # With a snapshot the state is replaced; without one only the gap is recorded.
      def on_log_gap(state, data)
        following = data[:snapshot].nil? ? state : deep_copy(data[:snapshot])
        following[:gaps] << { from_seq: data[:from_seq], to_seq: data[:to_seq] }
        following
      end

      # Copy the snapshot so later writes do not mutate the entry. Plain JSON data, so Marshal is a
      # safe deep copy.
      def deep_copy(value)
        Marshal.load(Marshal.dump(value))
      end
    end
  end
end
