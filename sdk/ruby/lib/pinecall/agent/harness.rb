# frozen_string_literal: true

require "json"

module Pinecall
  class Agent
    # The judges and the personas a class owns: `judges on: [...]` and `personas on: [...]` name which of
    # Pinecall's its calls meet and its runs play; its own are the files beside the class, read here.
    module Harness
      # The name a judge or a persona is called by: lower-case words joined by hyphens.
      A_NAME = /\A[a-z0-9]+(?:-[a-z0-9]+)*\z/

      ANSWERS = %w[verdict choice score].freeze
      WHENS = %w[always simulations trigger].freeze
      READS = %w[prompt evidence facts].freeze
      # Fewer than two is not a choice.
      FEWEST_CHOICES = 2

      NOT_A_PAGE = "a judge opens with its front matter between two --- lines, and the question below"
      NO_QUESTION = "a judge asks a question of a call: write one below the front matter"
      NO_CHOICES = "a judge that answers one of several needs at least two choices"
      CHOICES_ONLY = "only a judge that answers one of several takes choices"
      NO_TRIGGER = "a judge that runs on a trigger needs the trigger's question"
      NOT_A_PERSONA = "a persona is a JSON object with a goal and a style"
      NO_GOAL = "a persona wants something: write its goal, in the first person"
      NO_STYLE = "a persona talks some way: write its style"

      module_function

      # What `judges` and `personas` declare, the folders beside the class read into each `own`. A
      # folder with files and no declaration is refused: a judge nobody declared would run on no call.
      def declared(klass, folder:)
        found = {}
        judge_files = folder ? read_judge_files(File.join(folder, "judges")) : []
        switches = klass.environment[:judges]
        if switches
          found[:judges] = with_files(switches, judge_files)
        elsif !judge_files.empty?
          raise DeclarationRefused, "#{File.join(folder, 'judges')} holds #{judge_files.size} judge(s) and the class declares none: " \
                                    'judges on: ["consent", …] declares them, and which of Pinecall\'s run'
        end
        persona_files = folder ? read_persona_files(File.join(folder, "test", "personas")) : []
        switches = klass.environment[:personas]
        if switches
          found[:personas] = with_files(switches, persona_files)
        elsif !persona_files.empty?
          raise DeclarationRefused, "#{File.join(folder, 'test', 'personas')} holds #{persona_files.size} persona(s) and the class " \
                                    'declares none: personas on: ["in-a-hurry", …] declares them, and which of Pinecall\'s play'
        end
        found
      end

      # Every `<name>.md` under the folder as a judge, refused by sentence; none for no folder.
      def read_judge_files(folder)
        return [] unless File.directory?(folder)

        Dir.children(folder).sort.select { |name| name.end_with?(".md") }.map do |name|
          judge_of(File.join(folder, name), File.read(File.join(folder, name), encoding: "utf-8"))
        end
      end

      # Every `<name>.json` under the folder as a persona, refused by sentence; none for no folder.
      def read_persona_files(folder)
        return [] unless File.directory?(folder)

        Dir.children(folder).sort.select { |name| name.end_with?(".json") }.map do |name|
          persona_of(File.join(folder, name), File.read(File.join(folder, name), encoding: "utf-8"))
        end
      end

      # A judge file: the library's own format, front matter between two `---` lines and the question below.
      def judge_of(path, text)
        shown = File.basename(path)
        name = File.basename(path, ".md")
        fields, body = page(shown, text)
        refuse(shown, "\"#{name}\" is not a judge's name: lower-case words joined by hyphens, like offers-next-slot") unless A_NAME.match?(name)
        if fields.key?("name") && fields["name"] != name
          refuse(shown, "its front matter says name: #{fields['name']}, and the file is #{shown}: the file's name is the judge's")
        end
        question = body.strip
        refuse(shown, NO_QUESTION) if question.empty?
        answer = one_of(shown, "answer", fields.fetch("answer", "verdict"), ANSWERS)
        choices = listed(fields.fetch("choices", ""))
        refuse(shown, NO_CHOICES) if answer == "choice" && choices.size < FEWEST_CHOICES
        refuse(shown, CHOICES_ONLY) if answer != "choice" && !choices.empty?
        on = one_of(shown, "when", fields.fetch("when") { fields.fetch("on", "always") }, WHENS)
        trigger = fields.fetch("trigger", "")
        refuse(shown, NO_TRIGGER) if on == "trigger" && trigger.strip.empty?
        reads = listed(fields.fetch("reads", "")).map { |read| one_of(shown, "reads", read, READS) }
        { name:, question:, answer:, choices:, when: on, trigger:, reads: }
      end

      # A persona file: JSON, what `PUT …/personas/{name}` takes, the name being the file's.
      def persona_of(path, text)
        shown = File.basename(path)
        name = File.basename(path, ".json")
        refuse(shown, "\"#{name}\" is not a persona's name: lower-case words joined by hyphens, like price-shopper") unless A_NAME.match?(name)
        begin
          given = JSON.parse(text)
        rescue JSON::ParserError => e
          refuse(shown, "not JSON: #{e.message}")
        end
        refuse(shown, NOT_A_PERSONA) unless given.is_a?(Hash)
        refuse(shown, NO_GOAL) unless given["goal"].is_a?(String) && !given["goal"].strip.empty?
        refuse(shown, NO_STYLE) unless given["style"].is_a?(String) && !given["style"].strip.empty?
        if given.key?("name") && given["name"] != name
          refuse(shown, "it says its name is #{given['name']}, and the file is #{shown}: the file's name is the persona's")
        end
        persona = Wire::Codec.symbolize({ **given, "name" => name })
        begin
          Wire::Validate.call!("PersonaDeclaration", persona, where: shown)
        rescue Wire::WireError => e
          refuse(shown, e.message)
        end
        persona
      end

      def with_files(switches, files)
        { on: Array(switches[:on]), own: [*Array(switches[:own]), *files] }
      end

      def page(shown, text)
        _, opened, rest = text.partition("---\n")
        head, closed, body = rest.partition("\n---\n")
        refuse(shown, NOT_A_PAGE) if opened.empty? || closed.empty?
        fields = {}
        head.each_line do |line|
          key, colon, value = line.partition(":")
          fields[key.strip] = value.sub(/\s+#.*\z/, "").strip if !colon.empty? && !line.strip.empty?
        end
        [fields, body]
      end

      # A list is `[a, b]` or `a, b`; the library writes the second.
      def listed(value)
        value.delete_prefix("[").delete_suffix("]").split(",").map(&:strip).reject(&:empty?)
      end

      def one_of(shown, field, value, allowed)
        refuse(shown, "#{field} is \"#{value}\", not one of #{allowed.join(', ')}") unless allowed.include?(value)
        value
      end

      def refuse(shown, sentence)
        raise DeclarationRefused, "#{shown}: #{sentence}"
      end
    end
  end
end
