# frozen_string_literal: true

require "socket"

# Fake REST gateway: one canned answer per `"METHOD /path"`; records every request.
class RestGateway
  Asked = Data.define(:method, :path, :headers, :body)

  attr_reader :asked

  def initialize(answers)
    @answers = answers
    @asked = []
    @server = TCPServer.new("127.0.0.1", 0)
    @thread = Thread.new { serve }
  end

  def url = "http://127.0.0.1:#{@server.addr[1]}"

  def stop
    @thread.kill
    @server.close
  end

  private

  def serve
    loop do
      socket = @server.accept
      Thread.new { answer(socket) }
    end
  rescue IOError, Errno::EBADF
    nil
  end

  def answer(socket)
    method, target, = socket.gets.split
    headers = {}
    while (header = socket.gets) && header !~ /\A\r?\n\z/
      name, _, value = header.partition(":")
      headers[name.strip.downcase] = value.strip
    end
    length = headers["content-length"].to_i
    raw = length.positive? ? socket.read(length) : nil
    @asked << Asked.new(method:, path: target, headers:, body: raw && JSON.parse(raw, symbolize_names: true))
    status, body = @answers.fetch("#{method} #{target}") { [404, { detail: "no door at #{target}" }] }
    text = JSON.generate(body)
    socket.write("HTTP/1.1 #{status} X\r\ncontent-type: application/json\r\n" \
                 "content-length: #{text.bytesize}\r\nconnection: close\r\n\r\n#{text}")
  rescue Errno::EPIPE, IOError
    nil
  ensure
    socket.close unless socket.closed?
  end
end
