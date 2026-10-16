# frozen_string_literal: true

require "socket"

# A gateway on a real TCP/WebSocket socket: answers register, configure and drain, records every
# frame and the headers the socket came with, and sends an app whatever entry a test says.
class FakeGateway
  attr_reader :frames, :authorization, :world
  # False: a drain is heard and never answered, as a gateway that went quiet.
  attr_accessor :answers_drains
  # Slugs whose registration is refused, as a gateway refuses a slug that belongs to another org.
  attr_accessor :taken

  def initialize
    @server = TCPServer.new("127.0.0.1", 0)
    @frames = Thread::Queue.new
    @sockets = []
    @drivers = []
    @seq = 0
    @answers_drains = true
    @thread = Thread.new { serve }
  end

  def url = "http://127.0.0.1:#{@server.addr[1]}"

  def stop
    @thread.kill
    @sockets.each { |socket| socket.close rescue nil } # rubocop:disable Style/RescueModifier
    @server.close
  end

  # Send every connected app one entry, as the gateway writes it.
  def send_entry(agent, type, data, call: nil)
    @drivers.each { |driver| write(driver, agent, type, data, call:) }
  end

  # The next frame of this type an app sent, waiting for it.
  def next_frame(type, within_s: 5)
    deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + within_s
    loop do
      frame = @frames.pop(timeout: [deadline - Process.clock_gettime(Process::CLOCK_MONOTONIC), 0].max)
      return frame if frame.nil? || frame[:type] == type
    end
  end

  private

  def serve
    loop do
      socket = @server.accept
      @sockets << socket
      Thread.new { talk(socket) }
    end
  rescue IOError, Errno::EBADF
    nil
  end

  def talk(socket)
    driver = WebSocket::Driver.server(Writer.new(socket))
    driver.on(:connect) do
      @authorization = driver.env["HTTP_AUTHORIZATION"]
      @world = driver.env["HTTP_PINECALL_ENV"]
      driver.start
      @drivers << driver
    end
    driver.on(:message) { |event| took(driver, event.data) }
    loop { driver.parse(socket.readpartial(4096)) }
  rescue EOFError, IOError, Errno::ECONNRESET
    nil
  end

  def took(driver, raw)
    frame = JSON.parse(raw, symbolize_names: true)
    @frames << frame
    case frame[:type]
    when "agent.register"
      if (taken || []).include?(frame[:agent])
        write(driver, frame[:agent], "error", { code: "bad_shape", message: "agent #{frame[:agent]} belongs to another org: a slug is one org's",
                                                 command: "agent.register", id: frame[:id], recoverable: true })
      else
        write(driver, frame[:agent], "agent.registered", { app: "app_1", routes: frame[:data][:routes] })
      end
    when "agent.configure"
      write(driver, frame[:agent], "agent.configured", { changed: %w[tools] })
    when "agent.drain"
      return unless answers_drains

      write(driver, frame[:agent], "agent.draining", { app: "app_1", env: "sandbox", handed: 0, parked: 0 })
    end
  end

  def write(driver, agent, type, data, call: nil)
    @seq += 1
    driver.text(JSON.generate({ seq: @seq, ts: Time.now.to_f, call:, agent:, type:, ephemeral: false, data: }))
  end

  # websocket-driver needs an object with `write` and `url`.
  Writer = Struct.new(:socket) do
    def write(bytes) = socket.write(bytes)
  end
end
