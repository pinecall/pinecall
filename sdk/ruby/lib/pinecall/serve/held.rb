# frozen_string_literal: true

# The agents a process holds, and leaving: a drain, then the socket closed, once.

module Pinecall
  module Serve
    # What `Pinecall.serve` and `serve start` hold: the client, the agents mounted on it.
    class Held
      attr_reader :client, :mounted

      def initialize(client, mounted, err: $stderr)
        @client = client
        @mounted = mounted
        @err = err
        @stopped = Thread::Queue.new
        @lock = Mutex.new
        @drained = nil
      end

      # Drain every agent, close the socket and say on stderr where the calls went; asked twice, the
      # first answer. Returns the drain.
      def stop
        @lock.synchronize do
          return @drained unless @drained.nil?

          @drained = @client.drain
          close
          @err.puts(Serve.drain_line(@drained))
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
