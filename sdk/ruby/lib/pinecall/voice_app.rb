# frozen_string_literal: true

module Pinecall
  # A voice app: the numbers a project answers, the agent that answers each, and what they share.
  # `line`, `rule`, `silence`, `on` and `page` return the app, so they chain.
  class VoiceApp
    A_NAME = /\A[a-z0-9][a-z0-9-]*\z/
    A_NUMBER = /\A\+[1-9]\d{6,14}\z/
    SECONDS = /\A(\d+)s\z/
    A_ZONE = %r{\A(UTC|[A-Z][A-Za-z_]+(/[A-Za-z0-9_+-]+)+)\z}
    # The type of the entry a line an agent logs is kept as: its own name is inside it.
    A_LOGGED_LINE = "custom"

    NOT_A_NUMBER = "a line is a phone number with its country code, like +1 415 555 0134"
    NOT_A_PAGE = "a page is the folder its build writes, inside the project: app.page(\"ui/dist\")"
    NOT_A_SILENCE = "silence is after: in seconds (8, or \"8s\") and say: the words to a caller who went quiet"

    # One number of the app and who answers it.
    Line = Data.define(:number, :answers, :team, :greeting, :chooses)
    # The app's page: the built folder the platform serves, and the agent a visitor reaches.
    Page = Data.define(:dir, :answers)
    # The call an entry belongs to, as a handler is told it; `id` is nil for an entry of no call.
    Heard = Data.define(:id, :agent)

    # The apps made in this process, in order: the serve entry finds the one `app.rb` made.
    def self.made = @made ||= []

    attr_reader :name, :timezone, :lines, :rules, :paged

    def initialize(name, timezone: nil)
      raise DeclarationRefused, "a voice app's name is lowercase letters, digits and dashes, like its project's folder" unless A_NAME.match?(name.to_s)
      # The shape alone: Ruby carries no zone database, and the runtime checks the zone again.
      unless timezone.nil? || A_ZONE.match?(timezone.to_s)
        raise DeclarationRefused, "a voice app's timezone is an IANA zone, like America/Los_Angeles"
      end

      @name = name.to_s
      @timezone = timezone
      @lines = []
      @rules = []
      @paged = nil
      @silence = nil
      @hearing = Hash.new { |all, key| all[key] = [] }
      @starting = Hash.new { |all, key| all[key] = [] }
      VoiceApp.made << self
    end

    # Answer `number` with an agent: `app.line("+14155550134", FrontDesk, greeting: "Brightside.")`.
    # `answers` may be a lambda of the call that picks one of `team`, with `fallback` the agent the number is pointed at.
    def line(number, answers, greeting: nil, team: [], fallback: nil)
      dialled = number.to_s.gsub(/[\s().-]/, "")
      raise DeclarationRefused, NOT_A_NUMBER unless A_NUMBER.match?(dialled)
      raise DeclarationRefused, "#{dialled} is a line of #{@name} already" if @lines.any? { |line| line.number == dialled }

      chooses = agent?(answers) ? nil : answers
      bound = chooses.nil? ? answers : fallback
      raise DeclarationRefused, "a line is answered by an agent class: app.line(number, FrontDesk)" unless chooses.nil? || chooses.respond_to?(:call)
      raise DeclarationRefused, "#{dialled}: a line whose answers is a lambda names its fallback, the agent the number is pointed at" unless agent?(bound)
      raise DeclarationRefused, "the greeting of #{dialled} is the words the call opens with" if !greeting.nil? && greeting.strip.empty?

      other = @lines.find { |line| line.answers == bound && line.greeting != greeting }
      raise DeclarationRefused, "#{bound} answers #{other.number} and #{dialled}: both lines open with the same greeting, or with none" unless other.nil?

      team.each do |mate|
        raise DeclarationRefused, "#{mate} is of the team of #{dialled} and says nothing of what it takes: takes \"…\"" if mate.declared_takes.nil?
      end
      raise DeclarationRefused, "#{dialled}: a lambda answers with one of the line's team, and this line names none" if !chooses.nil? && team.empty?

      @lines << Line.new(number: dialled, answers: bound, team: team.dup.freeze, greeting:, chooses:)
      self
    end

    # A rule every agent of the app keeps: read into each one's prompt, and judged.
    def rule(rule)
      raise DeclarationRefused, "a rule is a sentence every agent of the app keeps" if rule.to_s.strip.empty?

      @rules << rule.strip
      self
    end

    # Run the block (or start the flow) on every entry of that name on a call of the app's agents.
    def on(name, flow = nil, &handler)
      name = name.to_s
      raise DeclarationRefused, "app.on takes the name of an entry, and a block or the flow it starts" if name.strip.empty? || (flow.nil? == handler.nil?)

      if flow.nil?
        @hearing[name] << handler
      else
        if flows.any? { |one| one.name == flow.name && !one.equal?(flow) }
          raise DeclarationRefused, "two flows of #{@name} are named #{flow.name}: a run is kept by its flow's name"
        end

        @starting[name] << flow
      end
      self
    end

    # The app's page: `app.page("ui/dist")`, served by the platform at the app's own name.
    def page(dir, answers: nil)
      folder = dir.to_s.delete_prefix("./").chomp("/")
      raise DeclarationRefused, NOT_A_PAGE if folder.empty? || folder.start_with?("/") || folder.split("/").include?("..")
      raise DeclarationRefused, "#{@name} has its page already, #{@paged.dir}: an app has one" unless @paged.nil?

      reached = answers || @lines.first&.answers
      raise DeclarationRefused, "a page's visitors reach an agent: write a line before the page, or name one with page(dir, answers: FrontDesk)" unless agent?(reached)

      @paged = Page.new(dir: folder, answers: reached)
      self
    end

    # What every agent of the app says to a caller who went quiet, and after how long.
    def silence(after:, say:, times: nil)
      seconds = seconds_of(after)
      raise DeclarationRefused, NOT_A_SILENCE if seconds.nil? || say.to_s.strip.empty? || (!times.nil? && times < 1)

      @silence = { says: [say], after_s: seconds, times: }.compact
      self
    end

    # Every flow the app starts, once each.
    def flows = @starting.values.flatten.uniq

    # The flows an entry of that name starts.
    def started_by(name) = @starting.fetch(name.to_s, [])

    # The name an entry is heard by and what it carries: a logged line by its own name.
    def named(type, data)
      return [type.to_s, data] unless type.to_s == A_LOGGED_LINE

      [data[:name].to_s, data[:data].is_a?(Hash) ? data[:data] : {}]
    end

    # Hand one entry to whoever asked for its name; a handler that raises is told to `failed`.
    def heard(type, call, agent, data, failed)
      name, carried = named(type, data)
      @hearing.fetch(name, []).each do |handler|
        handler.call(Heard.new(id: call, agent:), carried)
      rescue StandardError => e
        failed.call(name, e)
      end
    end

    # Every agent class the app names, once each.
    def agents = [*@lines.flat_map { |line| [line.answers, *line.team] }, *@paged&.answers].uniq

    # The lambda that picks who serves each call of the line `klass` is bound to.
    def choosing(klass) = @lines.find { |line| line.answers == klass && !line.chooses.nil? }&.chooses

    # The agents a call of `klass` may pass between; empty for an agent of no team.
    def team_of(klass)
      @lines.select { |line| line.team.any? && (line.answers == klass || line.team.include?(klass)) }
            .flat_map { |line| [line.answers, *line.team] }.uniq
    end

    # The numbers `klass` answers.
    def numbers_of(klass) = @lines.select { |line| line.answers == klass }.map(&:number)

    # What the app adds to one agent's declaration; a setting both declare is refused.
    def declares(klass)
      added = {}
      greeting = @lines.find { |line| line.answers == klass && !line.greeting.nil? }&.greeting
      unless greeting.nil?
        once(klass, :greeting, "its line's greeting")
        added[:greeting] = { say: greeting }
      end
      return added unless agents.include?(klass)

      added[:timezone] = once(klass, :timezone, "its own timezone") && @timezone unless @timezone.nil?
      added[:judges] = judging(klass) if @rules.any?
      added[:idle] = once(klass, :idle, "app.silence") && @silence unless @silence.nil?
      added
    end

    private

    def agent?(given) = given.is_a?(Class) && given < Agent

    def once(klass, field, app_says)
      return true if klass.environment[field].nil?

      raise DeclarationRefused, "#{klass} declares #{field} and #{@name} declares #{app_says}: keep one of the two"
    end

    # The class's own judges stay, and each rule adds one: a declared list is the agent's whole list.
    def judging(klass)
      own = klass.environment[:judges] || {}
      asked = @rules.each_with_index.map do |rule, at|
        Pinecall.own_judge(name: "app-rule-#{at + 1}", asks: "Did the agent keep this rule through the whole call: \"#{rule}\"?")
      end
      { on: own[:on] || [], own: [*own[:own], *asked] }
    end

    def seconds_of(given)
      return given.to_f if given.is_a?(Numeric) && given.positive?

      found = SECONDS.match(given.to_s.strip)
      found && found[1].to_f
    end
  end

  class << self
    # A voice app named as its project: `APP = Pinecall.voice_app("brightside", timezone: "America/Los_Angeles")`.
    def voice_app(name, timezone: nil) = VoiceApp.new(name, timezone:)
  end
end
