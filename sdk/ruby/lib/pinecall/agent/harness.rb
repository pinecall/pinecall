# frozen_string_literal: true

module Pinecall
  class Agent
    # The judges a class owns and the callers its test folder holds: `Pinecall.own_judge`, `Pinecall.own_persona`,
    # each refused by sentence when wrong; what `judges on:, own:` declares and what `test/personas.rb` holds, as
    # the declaration sends it.
    module Harness
      # The name a judge or a persona is called by: lower-case words joined by hyphens.
      A_NAME = /\A[a-z0-9]+(?:-[a-z0-9]+)*\z/

      ANSWERS = %w[verdict choice score].freeze
      WHENS = %w[always simulations trigger].freeze
      READS = %w[prompt evidence facts].freeze
      # Fewer than two is not a choice.
      FEWEST_CHOICES = 2

      NO_QUESTION = "a judge asks a question of a call: write it as asks"
      NO_CHOICES = "a judge that answers one of several needs at least two choices"
      CHOICES_ONLY = "only a judge that answers one of several takes choices"
      NO_TRIGGER = "a judge that runs on a trigger needs the trigger's question"
      NO_GOAL = "a persona wants something: write its goal, in the first person"
      NO_STYLE = "a persona talks some way: write its style"
      NOT_DECLARED_SO = "personas are held in test/personas.rb beside the goldens, ON for Pinecall's and each Pinecall.own_persona " \
                        "the agent's own, and judges are declared in the class with judges on: [...], own: [...]; " \
                        "a class that still names its personas writes personas on: [...], own: [...]"
      NOT_NAMES = "ON is the names of Pinecall's callers the agent is tested with, an array of strings"
      # What a served agent is told once when its class still names its callers: they play, and their place is the file.
      CALLERS_MOVED = "its personas are declared in the class, which still works: their place is now test/personas.rb beside the " \
                      "goldens — every Pinecall.own_persona it defines is the agent's own, and ON names Pinecall's"

      # What `own_persona` makes: a persona as the wire carries it, told by its class from whatever else a
      # `test/personas.rb` defines.
      class OwnPersona < Hash
      end

      module_function

      # A judge of the agent's own, refused by sentence when wrong; `own:` of `judges` takes it. `when:` is
      # always, simulations or trigger (asked only when `trigger:` is answered yes); `reads:` prompt, evidence, facts.
      def own_judge(name:, asks:, answer: "verdict", choices: [], trigger: "", reads: [], **rest)
        runs = rest.delete(:when) || "always"
        raise DeclarationRefused, "a judge takes no #{rest.keys.join(', ')}" unless rest.empty?
        raise DeclarationRefused, "\"#{name}\" is not a judge's name: lower-case words joined by hyphens, like offers-next-slot" unless name.is_a?(String) && A_NAME.match?(name)

        question = asks.to_s.strip
        refuse(name, NO_QUESTION) if question.empty?
        picked = one_of(name, "answer", answer.to_s, ANSWERS)
        listed = Array(choices).map(&:to_s)
        refuse(name, NO_CHOICES) if picked == "choice" && listed.size < FEWEST_CHOICES
        refuse(name, CHOICES_ONLY) if picked != "choice" && !listed.empty?
        on = one_of(name, "when", runs.to_s, WHENS)
        refuse(name, NO_TRIGGER) if on == "trigger" && trigger.to_s.strip.empty?
        read = Array(reads).map { |one| one_of(name, "reads", one.to_s, READS) }
        { name:, question:, answer: picked, choices: listed, when: on, trigger: trigger.to_s, reads: read }
      end

      # A caller of the agent's own — what `PUT …/personas/{name}` takes — refused by sentence when wrong.
      def own_persona(name:, goal:, style:, **rest)
        raise DeclarationRefused, "\"#{name}\" is not a persona's name: lower-case words joined by hyphens, like price-shopper" unless name.is_a?(String) && A_NAME.match?(name)

        refuse(name, NO_GOAL) unless goal.is_a?(String) && !goal.strip.empty?
        refuse(name, NO_STYLE) unless style.is_a?(String) && !style.strip.empty?
        persona = Wire::Codec.symbolize({ name:, goal:, style:, **rest })
        begin
          Wire::Validate.call!("PersonaDeclaration", persona, where: name)
        rescue Wire::WireError => e
          refuse(name, e.message)
        end
        OwnPersona[persona]
      end

      # The judges a class declares and the callers it is tested with, as the declaration sends them; nothing for a
      # class with neither.
      def declared(klass)
        found = {}
        switches = klass.environment[:judges]
        found[:judges] = roster("judge", switches) { |one| own_judge(**judge_input_of(one)) } if switches
        callers = personas_of(klass)
        found[:personas] = callers unless callers.nil?
        found
      end

      # The roster its `test/personas.rb` holds, or the class's own for one that still names its callers and has no file.
      def personas_of(klass)
        return klass.tested_with unless klass.tested_with.nil?

        switches = klass.environment[:personas]
        roster("persona", switches) { |one| own_persona(**one) } if switches
      end

      # The roster a `test/personas.rb` holds, read off the module it was loaded in: every `Pinecall.own_persona`
      # among its constants is the agent's own, in the order written, and `ON` names Pinecall's. Any other
      # constant is not a caller.
      def roster_in(held, file)
        on = held.const_defined?(:ON, false) ? held.const_get(:ON, false) : []
        raise DeclarationRefused, "#{file}: #{NOT_NAMES}" unless on.is_a?(Array) && on.all?(String)

        # `constants` answers in no order of its own.
        written = held.constants(false).sort_by { |name| held.const_source_location(name, false) }
        own = written.map { |name| held.const_get(name, false) }.grep(OwnPersona)
        roster("persona", { on:, own: }) { |one| own_persona(**one) }
      end

      # The class is tested with the roster its `test/personas.rb` holds; one that names its callers too is refused.
      def tested_with(klass, roster, file)
        if names_its_callers?(klass)
          raise DeclarationRefused, "#{klass} declares personas in the class and #{file} holds them too: " \
                                    "the file is their place — take personas out of the class"
        end

        klass.tested_with(roster)
      end

      # Whether the class names its callers itself, the old place for them.
      def names_its_callers?(klass) = !klass.environment[:personas].nil?

      # `on` as given, each of `own` checked once more and two of one name refused.
      def roster(what, switches)
        raise DeclarationRefused, NOT_DECLARED_SO unless switches.is_a?(Hash)

        own = Array(switches[:own]).map { |one| yield(Wire::Codec.symbolize(one)) }
        own.map { |one| one[:name] }.tally.each do |name, count|
          raise DeclarationRefused, "two #{what}s called #{name}: a name is declared once" if count > 1
        end
        { on: Array(switches[:on]), own: }
      end

      # A judge already built reads back as its input.
      def judge_input_of(one)
        begin
          Wire::Validate.call!("JudgeDeclaration", one, where: one[:name].to_s)
        rescue Wire::WireError => e
          refuse(one[:name], e.message)
        end
        { name: one[:name], asks: one[:question], answer: one.fetch(:answer, "verdict"), choices: one.fetch(:choices, []),
          when: one.fetch(:when, "always"), trigger: one.fetch(:trigger, ""), reads: one.fetch(:reads, []) }
      end

      def one_of(name, field, value, allowed)
        refuse(name, "#{field} is \"#{value}\", not one of #{allowed.join(', ')}") unless allowed.include?(value)
        value
      end

      def refuse(name, sentence)
        raise DeclarationRefused, "#{name}: #{sentence}"
      end
    end
  end

  class << self
    # A judge of the agent's own, for `judges own: [...]`: `Pinecall.own_judge(name: "offers-next-slot", asks: "…")`.
    def own_judge(**) = Agent::Harness.own_judge(**)

    # A caller of the agent's own, a constant of its `test/personas.rb`: `HURRIED = Pinecall.own_persona(name:, goal:, style:, …)`.
    def own_persona(**) = Agent::Harness.own_persona(**)
  end
end
