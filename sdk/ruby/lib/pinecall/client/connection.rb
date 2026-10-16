# frozen_string_literal: true

module Pinecall
  class Client
    # The gateway websocket: auth, reconnect with backoff, heartbeat, and one reader thread.
    #
    # The key goes in the `Authorization` header, never the URL (URLs end up in access logs).
    # A bad key closes with 1008 and no body. `websocket-driver` handles framing over a plain
    # TCP/TLS socket, so no event loop is needed.
    class Connection
      FIRST_WAIT_S = 0.5
      LONGEST_WAIT_S = 30.0
      GROWS_BY = 2
      PINGS_EVERY_S = 30

      Handlers = Data.define(:on_open, :on_entry, :on_error, :on_heartbeat)

      attr_reader :url

      def initialize(url:, api_key:, handlers:, env: nil, ping_every: PINGS_EVERY_S, backoff: {})
        @url = Endpoints.apps(url)
        @api_key = api_key
        @env = env
        @handlers = handlers
        @ping_every = ping_every
        @backoff = { first: FIRST_WAIT_S, longest: LONGEST_WAIT_S, grows_by: GROWS_BY }.merge(backoff)
        @lock = Mutex.new
        @open = false
        @closed = false
        @attempt = 0
      end

      def open? = @open

      # Connect and return once `on_open` has run; reconnects are handled internally afterwards.
      def start
        @closed = false
        @opened = Thread::Queue.new
        @reader = Thread.new { dial_until_closed }
        @reader.abort_on_exception = false
        answer = @opened.pop(timeout: 30)
        # Later failures go to `on_error`, not to this caller.
        @opened = nil
        raise NotConnected, "the gateway did not answer in 30s: #{@url}" if answer.nil?
        raise answer if answer.is_a?(Exception)

        self
      end

      # Raises when disconnected instead of queueing: a queued command could land after its call ended.
      def send_frame(command)
        @lock.synchronize do
          raise NotConnected, "#{command.type}: the gateway is not connected" unless @open

          @driver.text(Wire.encode(command))
        end
      end

      # A drain was asked: the gateway closing the socket from now on is not dialled back.
      def leaving! = @leaving = true

      # Close without reconnecting.
      def close
        @closed = true
        @open = false
        @heartbeat&.kill
        @socket&.close
        # A stop is read on the reader thread itself, which cannot wait for its own end.
        @reader&.join(1) unless Thread.current.equal?(@reader)
        nil
      end

      # Called by websocket-driver.
      def write(bytes)
        @socket.write(bytes)
      rescue IOError, SystemCallError => e
        @handlers.on_error.call(e)
      end

      private

      def dial_until_closed
        until @closed
          begin
            dial
          rescue StandardError => e
            fail_the_first_dial(e)
          end
          break if @closed || @leaving

          sleep(wait_s)
        end
      end

      def dial
        @socket = connect_to(URI.parse(@url))
        @driver = WebSocket::Driver.client(self)
        @driver.set_header("Authorization", "Bearer #{@api_key}")
        @driver.set_header(Rest::ENV_HEADER, @env) unless @env.nil?
        @driver.on(:open) { opened }
        @driver.on(:message) { |event| took(event.data) }
        @driver.on(:close) { |event| shut(event) }
        @driver.start
        read_until_closed
      end

      def connect_to(url)
        port = url.port || (url.scheme == "wss" ? 443 : 80)
        socket = TCPSocket.new(url.host, port)
        return socket unless url.scheme == "wss"

        context = OpenSSL::SSL::SSLContext.new
        context.set_params(verify_mode: OpenSSL::SSL::VERIFY_PEER)
        tls = OpenSSL::SSL::SSLSocket.new(socket, context)
        tls.hostname = url.host
        tls.sync_close = true
        tls.connect
        tls
      end

      def read_until_closed
        loop do
          bytes = @socket.readpartial(4096)
          @driver.parse(bytes)
        end
      rescue EOFError, IOError, SystemCallError, OpenSSL::SSL::SSLError
        @open = false
      end

      # Registration runs on its own thread: this is the reader thread, and `agent.register` is
      # answered by an entry it has to read.
      def opened
        @open = true
        @attempt = 0
        @heartbeat = Thread.new { beat }
        Thread.new { declare }
      end

      def declare
        @handlers.on_open.call
        @opened&.push(:open)
      rescue StandardError => e
        # First connection: raise from `start`. Reconnect: report via `on_error`.
        @opened.nil? || @opened.closed? ? @handlers.on_error.call(e) : @opened.push(e)
      end

      def took(raw)
        @handlers.on_entry.call(Wire.decode_entry(JSON.parse(raw, symbolize_names: true)))
      rescue StandardError => e
        @handlers.on_error.call(e)
      end

      def shut(event)
        @open = false
        @heartbeat&.kill
        return if @closed

        # Only a failed first connection is reported to `start`; later closes just retry.
        return unless @opened && !@opened.closed? && @attempt.zero?

        @opened.push(NotConnected.new("the gateway refused the socket: closed with #{event.code}"))
      end

      def fail_the_first_dial(error)
        @open = false
        return @handlers.on_error.call(error) unless @opened && !@opened.closed? && @attempt.zero?

        @opened.push(NotConnected.new("#{@url}: #{error.message}"))
      end

      def beat
        loop do
          sleep(@ping_every)
          break unless @open

          @handlers.on_heartbeat.call
        end
      rescue StandardError => e
        @handlers.on_error.call(e)
      end

      # Full jitter, so clients do not reconnect in lockstep.
      def wait_s
        window = [@backoff[:longest], @backoff[:first] * (@backoff[:grows_by]**@attempt)].min
        @attempt += 1
        rand * window
      end
    end
  end
end
