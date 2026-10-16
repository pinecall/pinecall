# frozen_string_literal: true

# The agents a process holds, and leaving: a drain, then the socket closed, once.

module Pinecall
  module Serve
    # What `Pinecall.serve` and `serve start` hold: the client, the agents mounted on it.
    class Held
      attr_reader :client, :mounted

      def initialize(client, mounted)
        @client = client
        @mounted = mounted
        @stopped = Thread::Queue.new
        @lock = Mutex.new
        @drained = nil
      end

      # Drain every agent, then close the socket; asked twice, the first answer. Returns the drain.
      def stop
        @lock.synchronize do
          return @drained unless @drained.nil?

          @drained = @client.drain
          close
          @drained
        end
      end

      # Close without draining: a second signal, or a stop the gateway already made.
      def close
        @client.close
        @stopped.close
      end

      # Block until the socket is closed.
      def join = @stopped.pop
    end
  end
end
