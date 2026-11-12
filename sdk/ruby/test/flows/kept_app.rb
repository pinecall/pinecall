# frozen_string_literal: true

require "socket"

# A gateway's flows doors in memory, served on 127.0.0.1: the runs and events of one app.
class KeptApp
  WAITS = { "sleep" => "sleeping", "wait" => "waiting", "call" => "calling" }.freeze
  APP = "brightside"

  attr_reader :runs, :events, :heard, :asked
  attr_accessor :refuses, :staged, :down

  def initialize
    @runs = {}
    @keys = {}
    @events = []
    @heard = []
    @asked = []
    @refuses = nil
    @staged = 202
    @down = nil
    @server = TCPServer.new("127.0.0.1", 0)
    @thread = Thread.new { serve }
  end

  def door = Pinecall::Client::AppWork::Door.new(url: "http://127.0.0.1:#{@server.addr[1]}", api_key: "pk_test", env: nil, app: APP)

  def stop
    @thread.kill
    @server.close
  end

  # The step the run waits on comes to `result`, and the run is ready again.
  def wake(run, result)
    kept = @runs.fetch(run)
    step = kept[:steps].find { |one| !one[:over] }
    step[:over] = true
    step[:result] = result
    kept[:status] = "ready"
  end

  # Keep an event for the app, as its own backend sends one.
  def send_event(name, data)
    @events << { id: @events.length + 1, name:, data: }
    @events.length
  end

  private

  def serve
    loop { Thread.new(@server.accept) { |socket| answer(socket) } }
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
    body = length.positive? ? JSON.parse(socket.read(length), symbolize_names: true) : {}
    status, said = answered(method, URI.parse(target), body)
    text = said.nil? ? "" : JSON.generate(said)
    socket.write("HTTP/1.1 #{status} X\r\ncontent-type: application/json\r\ncontent-length: #{text.bytesize}\r\nconnection: close\r\n\r\n#{text}")
  ensure
    socket.close
  end

  def answered(method, uri, body)
    if uri.path.end_with?("/stages")
      @asked << "POST #{uri.path} #{JSON.generate(body)}"
      return [@staged, { call: "CA_1" }]
    end
    path = uri.path.delete_prefix("/v1/apps/#{APP}")
    @asked << "#{method} #{path}"
    parts = path.split("/").reject(&:empty?)
    return [200, { events: @events.reject { |one| @heard.include?(one[:id]) }, runs: @runs.values.select { |run| run[:status] == "ready" }.map { |run| deep(run) } }] if path == "/work"
    return [204, (@heard << parts[1].to_i) && nil] if parts[0] == "events"
    return started(body) if path == "/runs" && method == "POST"
    return listed(uri) if path == "/runs"

    run = @runs[parts[1]]
    return [404, { detail: "no such run" }] if run.nil?
    return [200, deep(run)] if parts.length == 2

    case parts[2]
    when "end" then run[:status] = body[:status]
    when "cancel" then run[:status] = "cancelled"
    when "steps"
      return [503, { detail: @down }] unless @down.nil?

      step(run, body)
    end
    [200, run.merge(steps: [])]
  end

  def started(body)
    key = "#{body[:flow]}:#{body[:key]}"
    return [201, @runs[@keys[key]]] if @keys.key?(key)

    run = { id: "run_#{@runs.length + 1}", flow: body[:flow], input: body[:input], status: "ready", steps: [] }
    @runs[run[:id]] = run
    @keys[key] = run[:id]
    [201, run]
  end

  def listed(uri)
    query = URI.decode_www_form(uri.query.to_s).to_h
    [200, { runs: @runs.values.select { |run| run[:flow] == query["flow"] && run[:status] == query["status"] }.map { |run| run.merge(steps: []) } }]
  end

  def step(run, body)
    kind = body[:kind]
    step = { seq: body[:seq], kind:, asked: body[:asked] || {}, over: false, result: nil }
    if %w[run emit].include?(kind)
      step.merge!(over: true, result: body[:result])
    elsif kind == "call" && !@refuses.nil?
      step.merge!(over: true, result: @refuses)
    else
      run[:status] = WAITS.fetch(kind)
    end
    send_event(step[:asked][:name], step[:asked][:data]) if kind == "emit"
    run[:steps] << step
  end

  def deep(run) = JSON.parse(JSON.generate(run), symbolize_names: true)
end
