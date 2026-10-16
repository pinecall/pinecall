# frozen_string_literal: true

# What a verb of the call waits for, and the answers it gets: a transfer, a supervisor, a search.

module Pinecall
  class CallWorld
    # Seconds `say`/`reply` wait for their turn before returning false.
    LANDS_WITHIN_S = 30
    # A transfer's far end may ring for 25 s before it fails.
    TRANSFER_WITHIN_S = 90
    # What `attention` waits beyond `wait_s` for the answer entry to arrive.
    A_MOMENT_S = 15
    # No answer came back: the gateway, not the far end, went quiet.
    NO_ANSWER = "the runtime never said how it went"
    # A pending verb when the call ends first.
    THE_CALL_ENDED = "the call ended before it was answered"
    # `search` on a call no gateway serves (an offline prompt, a test).
    NO_GATEWAY_TO_SEARCH = "this call cannot search: no gateway is serving it"

    # How a transfer went. `ok: false` means the caller is still with the agent.
    Transferred = Data.define(:to, :mode, :ok, :error)

    # Who took the line, or why nobody did.
    Attended = Data.define(:ok, :by, :error)

    # One search hit: its source path, heading and text.
    Found = Data.define(:path, :heading, :text)

    # The verbs waiting for an entry, by kind: `:spoken`, `:transfers`, `:asks`. The runtime always
    # answers with an entry; the ceiling only guards against a gateway that went away.
    class Waiting
      def initialize
        @waiting = Hash.new { |kinds, kind| kinds[kind] = [] }
        @lock = Mutex.new
      end

      # Block until the answer of this kind arrives, or return `lapsed` after `ceiling_s`.
      def wait(kind, ceiling_s, lapsed)
        answer = Thread::Queue.new
        @lock.synchronize { @waiting[kind] << answer }
        yield
        got = answer.pop(timeout: ceiling_s)
        got.nil? ? lapsed : got
      ensure
        @lock.synchronize { @waiting[kind].delete(answer) }
      end

      # Answer every verb waiting for this kind.
      def settle(kind, answer)
        @lock.synchronize { @waiting.delete(kind) || [] }.each { |waiting| waiting.push(answer) }
      end

      # The call ended: every verb waiting is answered now instead of at its ceiling.
      def end_all
        settle(:spoken, false)
        settle(:transfers, Transferred.new(to: "", mode: nil, ok: false, error: THE_CALL_ENDED))
        settle(:asks, Attended.new(ok: false, by: nil, error: THE_CALL_ENDED))
      end
    end
  end
end
