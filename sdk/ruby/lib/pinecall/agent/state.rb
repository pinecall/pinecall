# frozen_string_literal: true

module Pinecall
  class Agent
    # One recorded field assignment.
    Change = Data.define(:seq, :field, :prev, :next, :author, :at)

    # One named entry the agent appended to the call's log.
    LogEntry = Data.define(:seq, :name, :data, :at)

    # Declared state fields. The writer each `state` macro generates records every change.
    module State
      module Declaring
        # Declare a state field and its initial value.
        #
        #     state :patient, visibility: :pii  # nil until a tool finds one
        #     state :slots, []                  # a list of its own, per call
        #     state(:identified) { !patient.nil? }
        #
        # A block makes the field derived: readable like any other, never assignable.
        #
        # @param visibility [Symbol] `:public`, `:tenant` or `:pii`; omitted means the wire
        #   default (`tenant`) and nothing is sent.
        def state(name, default = nil, visibility: nil, &derived)
          name = name.to_sym
          refuse_a_name_that_is_taken(name)
          state_visibility[name] = visibility unless visibility.nil?
          if derived
            derived_state[name] = derived
            define_method(name) { instance_exec(&self.class.derived_state[name]) }
            return name
          end
          declared_state[name] = default
          define_method(name) { @state[name] }
          define_method(:"#{name}=") { |value| write_state(name, value) }
          name
        end

        # Declare the `stage` field and its values; the first is the initial one.
        #
        #     stage :identify, :choose, :book, :done
        #
        # A tool's `stage:` naming an undeclared stage is refused at load, since that tool
        # could never be visible.
        def stage(*names)
          raise DeclarationRefused, "stage names the values the stage may hold; give at least one" if names.empty?

          @stages = names.map(&:to_sym)
          state(:stage, @stages.first)
          @stages
        end

        # The declared stage values, inherited if not declared here.
        def stages
          @stages || (superclass.respond_to?(:stages) ? superclass.stages : nil)
        end

        # Declared fields and initial values, including inherited ones.
        def declared_state
          @declared_state ||= inherit(:declared_state)
        end

        # Derived fields by name.
        def derived_state
          @derived_state ||= inherit(:derived_state)
        end

        # Visibility by field, for fields that declared one.
        def state_visibility
          @state_visibility ||= inherit(:state_visibility)
        end

        def state_names = declared_state.keys + derived_state.keys

        private

        def inherit(what)
          superclass.respond_to?(what) ? superclass.public_send(what).dup : {}
        end

        def refuse_a_name_that_is_taken(name)
          return unless declared_state.key?(name) || derived_state.key?(name)

          raise DeclarationRefused, "#{self.name || "this agent"} declares #{name} twice"
        end
      end

      # ── instance methods ─────────────────────────────────────────────────────

      # A copy of the current state, derived fields included.
      def snapshot
        kept = @state.dup
        self.class.derived_state.each_key { |name| kept[name] = public_send(name) }
        kept
      end

      # Replace the state with a snapshot; fields missing from it are cleared. A stage that came
      # back as JSON is a string, and is the declared stage it names.
      def restore(state)
        state = state.transform_keys(&:to_sym)
        Author.with(Author.current || "restore") do
          self.class.declared_state.each_key do |name|
            value = state.key?(name) ? state[name] : nil
            write_state(name, name == :stage ? declared_stage(value) : value)
          end
        end
        self
      end


      # Merge the given fields over the current state (unlike `restore`, which clears the rest).
      def start_in(state)
        restore(snapshot.merge(state.transform_keys(&:to_sym)))
      end

      # Fields that differ between two snapshots.
      def diff(before, after = snapshot)
        (before.keys | after.keys).filter_map do |field|
          { field:, prev: before[field], next: after[field] } if before[field] != after[field]
        end
      end

      # Replace the change log with one summary entry; the state itself is untouched.
      def collapse(summary)
        at = now
        @changes.clear
        @changes << Change.new(seq: next_seq, field: "@summary", prev: nil, next: summary,
                               author: "collapse", at:)
        @changes.last
      end

      # Recorded changes, oldest first.
      def changes = @changes.dup

      # Subscribe to changes; the returned lambda unsubscribes.
      def on_change(&listener)
        @change_listeners << listener
        -> { @change_listeners.delete(listener) }
      end

      # Start recording changes; earlier writes are the baseline.
      def seal
        @sealed = true
        self
      end

      def sealed? = @sealed

      private

      def declared_stage(value)
        named = self.class.stages&.find { |stage| stage.to_s == value.to_s }
        named.nil? ? value : named
      end

      # Every state write goes through here; after `seal` a write without an author raises.
      def write_state(field, value)
        if @sealed
          author = Author.current
          raise UnauthoredWrite, field if author.nil?

          previous = @state[field]
          @state[field] = value
          # An equal value is not a change: no re-render, no log entry.
          return value if previous == value

          record(Change.new(seq: next_seq, field:, prev: previous, next: value, author:, at: now))
        else
          @state[field] = value
        end
        value
      end

      def record(change)
        @changes << change
        @change_listeners.each { |listener| listener.call(change) }
        change
      end

      def next_seq = @seq += 1

      def now = Time.now.to_f
    end
  end
end
