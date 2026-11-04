# frozen_string_literal: true

module Pinecall
  class Agent
    # The judges and the personas a class owns: `Pinecall.own_judge`, `Pinecall.own_persona`, each refused by
    # sentence when wrong, and what `judges on:, own:` and `personas on:, own:` declare, as the declaration sends it.
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
      NOT_DECLARED_SO = "judges and personas are declared with judges on: [...], own: [...] and personas on: [...], own: [...]"

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
        persona
      end

      # What `judges` and `personas` declare, as the declaration sends it; nothing for a class that declares neither.
      def declared(klass)
        found = {}
        switches = klass.environment[:judges]
        found[:judges] = roster("judge", switches) { |one| own_judge(**judge_input_of(one)) } if switches
        switches = klass.environment[:personas]
        found[:personas] = roster("persona", switches) { |one| own_persona(**one) } if switches
        found
      end

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

    # A caller of the agent's own, for `personas own: [...]`: `Pinecall.own_persona(name:, goal:, style:, …)`.
    def own_persona(**) = Agent::Harness.own_persona(**)
  end
end
