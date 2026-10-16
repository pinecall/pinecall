# frozen_string_literal: true

require_relative "agent/author"
require_relative "agent/doc"
require_relative "agent/state"
require_relative "agent/spec"
require_relative "agent/tools"
require_relative "agent/config"
require_relative "agent/knowledge"
require_relative "agent/searching"

module Pinecall
  # Base class for an agent: fields are state, `tool` methods are the model's tools, comments
  # are the prompt.
  #
  #     class ClinicaNorte < Pinecall::Agent
  #       language "es"
  #
  #       stage :identify, :book
  #       state :patient
  #
  #       # Busca al paciente por nombre y teléfono.
  #       tool stage: :identify, pii: %i[name phone]
  #       def find_patient(name:, phone:)
  #         self.patient = Agenda.find(name, phone)
  #         self.stage = :book if patient
  #         patient
  #       end
  #     end
  class Agent
    extend Config::Declaring
    extend State::Declaring
    extend Tools::Declaring
    extend Prompt::Declaring
    extend Panel::Declaring
    include State
    include Tools

    # Agent subclasses in definition order; `pinecall prompt agent.rb` uses it to find the class.
    def self.written = @written ||= []

    def self.inherited(subclass)
      super
      Agent.written << subclass
    end

    def initialize
      @state = {}
      @changes = []
      @change_listeners = []
      @log = []
      @log_listeners = []
      @event_listeners = []
      @seq = 0
      @sealed = false
      @call = nil
      @last_call = nil
      self.class.declared_state.each { |name, default| @state[name] = opening(default) }
    end

    # The call being served. A method, not a field, so it never reaches a view; raises outside a call.
    def call
      raise Error, "there is no call here: the bridge hands an agent its call when one starts" if @call.nil?

      @call
    end

    # Whether this instance is serving a call.
    def call? = !@call.nil?

    # The knowledge bases attached to this agent: `knowledge.search("…")` inside a tool.
    def knowledge = Knowledge.new(self)

    # Speak `text` verbatim now, as a `turn.agent`.
    def say(text, **options) = call.say(text, **options)

    # Make the model speak now, guided by instructions the caller does not hear.
    def reply(instructions, **options) = call.reply(instructions, **options)

    # Append a named entry to the call's log.
    def log(name, data = nil)
      entry = LogEntry.new(seq: next_seq, name: name.to_s, data:, at: Time.now.to_f)
      @log << entry
      @log_listeners.each { |listener| listener.call(entry) }
      entry
    end

    # Everything this agent has logged, oldest first.
    def logged = @log.dup

    # Subscribe to logged entries; the returned lambda unsubscribes.
    def on_log(&listener)
      @log_listeners << listener
      -> { @log_listeners.delete(listener) }
    end

    # Subscribe to external events, after `on_event` has run; the returned lambda unsubscribes.
    def on_heard(&listener)
      @event_listeners << listener
      -> { @event_listeners.delete(listener) }
    end

    # The contact's previous call, read from the store passed to `mount(last:)`.
    def last(contact)
      raise Error, "last(contact) needs a store: mount the agent with last: to give it one" if @last_call.nil?

      @last_call.call(contact)
    end

    # ── hooks: override them; state written inside one is attributed to the hook ──

    # A call started.
    def on_call(call) = nil

    # The call ended.
    def on_end(call) = nil

    # A declared external event arrived.
    def on_event(name, data, meta) = nil

    # Memory was written; persist the ops wherever the application keeps them.
    def on_memory(ops, call) = nil

    # ── called by the bridge ─────────────────────────────────────────────────

    # Run a hook with its state writes attributed to it.
    def run_hook(hook, *args)
      Author.with("hook:#{hook}") { public_send(hook, *args) }
    end

    # Set the call this instance serves; called once, at start.
    def serving(call)
      @call = call
      self
    end

    # Set the store `last(contact)` reads.
    def reads_last_from(source)
      @last_call = source
      self
    end

    # Notify `on_heard` listeners.
    def notify_heard(name, data, meta)
      @event_listeners.each { |listener| listener.call(name, data, meta) }
    end

    private

    # Initial value for a field: Procs are called and mutable defaults duped, so calls never share one.
    def opening(default)
      return default.call if default.is_a?(Proc)

      case default
      when Array, Hash, String then default.dup
      else default
      end
    end
  end
end
