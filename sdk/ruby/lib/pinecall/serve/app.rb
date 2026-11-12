# frozen_string_literal: true

module Pinecall
  module Serve
    # The project's voice app in its serve entry: loaded after its agents, described, its agents held.
    module App
      # A reload starts this process while the one before it drains, still on the port.
      PORT_TRIES = 90
      PORT_TRY_S = 0.5

      module_function

      # The voice app `app.rb` makes: the last `Pinecall.voice_app(…)` its loading made.
      def load_app(file)
        path = File.expand_path(file)
        raise CannotServe, "no voice app at #{path}" unless File.exist?(path)

        before = VoiceApp.made.dup
        begin
          load path
        rescue ScriptError, StandardError => e
          raise if e.is_a?(DeclarationRefused)

          raise CannotServe, "#{path} did not load: #{e.message}"
        end
        made = VoiceApp.made - before
        raise CannotServe, "#{path} makes one voice app: APP = Pinecall.voice_app(\"…\")" unless made.length == 1

        made.first
      end

      # Every agent served with its slug, and the app, loaded after them so it names their classes.
      def loaded(flags)
        classes = flags.served.map { |served| [served, Loading.load_served(served)] }
        return [classes, nil] if flags.app.nil?

        app = load_app(flags.app)
        app.agents.each do |klass|
          next if classes.any? { |_, one| one == klass }

          slugs = classes.map { |served, _| served.slug }.join(", ")
          raise CannotServe, "#{app.name} answers a line with #{klass}, and no agent served here is that class (#{slugs}): it is the Agent of its agents/<name>/agent.rb"
        end
        [classes, app]
      end

      # `serve app`: the app's name and page, one line of JSON, for a CLI that never loads it.
      def described(flags, out)
        classes, app = loaded(flags)
        raise CannotServe, "serve app takes --app, and one --slug for each --file" if app.nil?

        page = nil
        unless app.paged.nil?
          served, = classes.find { |_, klass| klass == app.paged.answers }
          raise CannotServe, "#{app.name}'s page reaches #{app.paged.answers}, which no agent is" if served.nil?

          page = { dir: app.paged.dir, agent: served.slug }
        end
        out.puts(JSON.generate({ name: app.name, page: }))
        0
      end

      # One agent held with what its app adds: its line's greeting, its team, the app's rules.
      def held(client, klass, slug, app, slugs, console:, err:)
        return Pinecall.mount(klass, client:, slug:, takes_unclaimed: !console) if app.nil?

        mates = app.team_of(klass)
        mounted = Pinecall.mount(klass, client:, slug:, takes_unclaimed: !console, declares: app.declares(klass),
                                        team: mates.empty? ? nil : mates.to_h { |mate| [mate, slugs.fetch(mate)] },
                                        rules: app.agents.include?(klass) ? app.rules : [], answers: app.choosing(klass))
        pointed(mounted, app.numbers_of(klass), err)
        mounted
      end

      # A number is the org's row: the app says who answers it, and the gateway says whether it is so.
      def pointed(mounted, numbers, err)
        told = []
        mounted.agent.on("agent.registered") do |registered, _|
          answered = (registered[:routes] || []).map { |route| route[:number] }
          (numbers - answered - told).each do |number|
            told << number
            err.puts("#{mounted.slug}  #{number} is not pointed at this agent yet: `pinecall numbers` says where it rings")
          end
        end
      end

      # The app's page served here, unless a runner hosts the process: the platform serves that one.
      def page_of(app, file, client, slugs, env, err)
        paged = app.paged
        agent = paged && slugs[paged.answers]
        return nil if agent.nil? || !env["PINECALL_HOST"].to_s.empty?

        port = Integer(env["PINECALL_PAGE_PORT"] || Paged::PORT)
        page = Paged.new(folder: File.join(File.dirname(File.expand_path(file)), paged.dir), agent:, url: client.url,
                         api_key: client.api_key, env: client.env, port:)
        PORT_TRIES.times do
          started = page.start
          err.puts("#{app.name}  its page is at http://localhost:#{port}")
          return started
        rescue Errno::EADDRINUSE
          sleep(PORT_TRY_S)
        end
        err.puts("#{app.name}  its page is not served: port #{port} is taken (PINECALL_PAGE_PORT moves it)")
        nil
      end
    end
  end
end
