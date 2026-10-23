# frozen_string_literal: true

require_relative "serve/loading"
require_relative "serve/held"
require_relative "serve/masking"
require_relative "serve/viewing"

module Pinecall
  # The entry the one `pinecall` CLI starts a Ruby agent with: `start` holds the agents and serves
  # their calls, `prompt` prints a prompt. The CLI runs it as
  # `ruby -r pinecall -e 'exit Pinecall::Serve.main(ARGV)' -- start --file … --slug …`.
  #
  # It reads its door from `PINECALL_URL`, `PINECALL_KEY` and `PINECALL_ENV` alone, and leaves on
  # SIGINT, SIGTERM or the end of its stdin, draining first; a second signal leaves now.
  module Serve
    USAGE = <<~USAGE
      usage: serve start --file <agent.rb> --slug <slug> [--file … --slug …] [--console] [--events] [--prod]
             serve prompt --file <agent.rb> --slug <slug> [--state field=json]… [--channel name] [--show-machine]
    USAGE

    NO_DOOR = "serve start reads PINECALL_URL and PINECALL_KEY from its environment, and one was not set"

    WORLDS = %w[sandbox production].freeze

    module_function

    # Run one verb and answer its exit status: 2 when it cannot run at all, with the sentence on `err`.
    def main(argv, out: $stdout, err: $stderr, env: ENV, input: $stdin, signals: nil)
      verb, *rest = argv
      case verb
      when "start" then start(Loading.parse(rest), out:, err:, env:, input:, signals:)
      when "prompt" then prompt(Loading.parse(rest), out:)
      else err.puts(USAGE) || 2
      end
    rescue CannotServe, NotConnected, Refused => e
      err.puts(e.message)
      2
    end

    # Hold every agent named until asked to leave; 0 once they drained.
    def start(flags, out:, err:, env:, input:, signals:)
      client = client_from(env, prod: flags.prod)
      classes = flags.served.map { |served| [served, Loading.load_served(served)] }
      mounted = classes.map do |served, klass|
        held = Pinecall.mount(klass, client:, slug: served.slug, takes_unclaimed: !flags.console)
        held.agent.on_dev { |verb, data| Viewing.answer(klass, served.slug, verb, data) }
        held
      end
      said(client, out:, err:, events: flags.events, maskings: mounted.to_h { |one| [one.slug, Masking.new(one.options)] })
      held = Held.new(client, mounted, err:)
      asked = signals || trapped
      client.on_stopped { |why| err.puts(why) || asked.push(:stopped) }
      client.connect
      Thread.new { ended(input, asked) }
      leave(held, asked)
    end

    # Load the class, open it in the state the pairs name, and print its prompt. No gateway, no key.
    def prompt(flags, out:)
      klass = Loading.load_served(flags.served.first)
      instance = klass.new.seal
      # A call of its own, so the channel's block is the one this channel and medium get.
      instance.serving(CallWorld.new(id: "", contact: "", channel: flags.channel, medium: flags.medium) { |*| nil })
      instance.start_in(flags.state) unless flags.state.empty?
      out.puts(Pinecall.show_prompt(instance, line: { channel: flags.channel }))
      out.puts("\n#{machine(instance)}") if flags.show_machine
      0
    end

    # The tools the class declares, marking the ones this state shows, under the stage.
    def machine(instance)
      shown = instance.visible_tools.map { |spec| spec[:name] }
      stage = instance.respond_to?(:stage) ? " stage: #{instance.stage}" : ""
      header = "#{Prompt.header_for("tools")}#{stage}"
      return "#{header}\n\n  this agent declares no tools" if instance.tools.empty?

      declared = instance.class.declared_tools.values
      width = declared.map { |one| one.name.length }.max
      lines = declared.map do |one|
        visible = shown.include?(one.name.to_s)
        "  #{visible ? "●" : "○"} #{one.name.to_s.ljust(width)}  #{gated_by(instance, one.options, visible)}"
      end
      [header, "", *lines].join("\n")
    end

    # What gates a tool: its stages, its `when`, or nothing. A tool hidden in its own stage is always
    # its `when`'s doing, and says so.
    def gated_by(instance, options, visible)
      stages = options[:stage] && Array(options[:stage]).map(&:to_sym)
      return options[:when].nil? ? "always" : "when(state)" if stages.nil?

      here = instance.respond_to?(:stage) ? instance.stage : nil
      named = stages.join(" · ")
      !visible && !here.nil? && stages.include?(here) ? "#{named} · when(state) says no" : named
    end

    # Where the calls went, and what became of the tools running: one line on stderr.
    def drain_line(drained)
      return "draining · no live calls" if drained.handed + drained.parked + drained.tools == 0

      parts = ["draining"]
      parts << "#{plural(drained.handed, "live call")} handed over" if drained.handed.positive?
      parts << "#{plural(drained.parked, "live call")} kept for the next process" if drained.parked.positive?
      parts << "#{plural(drained.finished, "tool")} finished" if drained.finished.positive?
      parts << "#{plural(drained.tools - drained.finished, "tool")} cut" if drained.tools > drained.finished
      parts.join(" · ")
    end

    def plural(count, noun) = "#{count} #{noun}#{count == 1 ? "" : "s"}"

    def client_from(env, prod:)
      url, key = env["PINECALL_URL"], env["PINECALL_KEY"]
      raise CannotServe, NO_DOOR if url.to_s.empty? || key.to_s.empty?

      world = prod ? "production" : env["PINECALL_ENV"]
      world = nil if world.to_s.empty?
      raise CannotServe, "PINECALL_ENV is sandbox or production, not #{world}" unless world.nil? || WORLDS.include?(world)

      client = Client.new(url:, api_key: key, env: world)
      # The name a hosted app's runner gave it: the gateway knows the release by it.
      client.host = env["PINECALL_HOST"] unless env["PINECALL_HOST"].to_s.empty?
      client
    end

    # Listening starts before connect, so `agent.registered` is the first line of a pipe. A pipe's
    # $stdout is buffered: each line is flushed, or the CLI waiting on it sees it only at exit.
    def said(client, out:, err:, events:, maskings:)
      client.on_entries do |entry|
        if events
          # What it prints is what the call's log keeps: a value the agent declared private never reaches a terminal.
          shown = maskings[entry.agent]&.entry(entry) || entry
          out.puts(JSON.generate({ type: shown.type, agent: shown.agent, call: shown.call, data: shown.data }))
        elsif entry.type == "agent.registered"
          out.puts("#{entry.agent}  · answering as #{entry.data[:app]}")
        end
        out.flush
      end
      client.on_errors { |error| err.puts("#{error.class}: #{error.message}") }
      client.on_killed { |slug, why| err.puts("#{slug}  ✗ #{why}") }
    end

    # A trap only pushes: the main thread does the leaving, as a trap may not take a lock.
    def trapped
      asked = Thread::Queue.new
      %w[INT TERM].each { |signal| Signal.trap(signal) { asked.push(:signalled) } }
      asked
    end

    # The process that started this one is gone when its end of the pipe closes.
    def ended(input, asked)
      input.read
    rescue IOError, SystemCallError
      nil
    ensure
      asked.push(:ended)
    end

    # The first reason drains (unless the org already stopped it); only a second signal closes at
    # once. The end of stdin is not one: the CLI passes a signal on and closes the pipe together.
    def leave(held, asked)
      if asked.pop == :stopped
        held.close
        return 0
      end
      outcome = Thread::Queue.new
      Thread.new { outcome.push(held.stop) }
      Thread.new do
        nil until asked.pop == :signalled
        outcome.push(:again)
      end
      held.close if outcome.pop == :again
      0
    end
  end
end
