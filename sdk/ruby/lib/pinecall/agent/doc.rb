# frozen_string_literal: true

module Pinecall
  class Agent
    # Reads the comment above a class or method from its source file; that comment is the prompt.
    #
    # Ruby drops `#` comments, so this uses `source_location` and walks up from the `def`,
    # skipping declaration macros in between:
    #
    #     # Busca al paciente por nombre y teléfono.
    #     tool stage: :identify, pii: %i[name phone]
    #     def find_patient(name:, phone:)
    #
    # A class built at runtime has no source file; it declares its text with `doc "…"`.
    module Doc
      # Stops the upward walk when no comment was found.
      ENDS_WHAT_CAME_BEFORE = /\A\s*(end\b|def\b|class\b|module\b)/
      COMMENT = /\A\s*#(?!\s*(frozen_string_literal|rubocop|:nodoc:))\s?(.*)\z/

      class << self
        # The comment above the class's `class` line, or nil.
        def for_class(klass)
          declared = klass.instance_variable_get(:@pinecall_doc)
          return declared unless declared.nil?
          return nil if klass.name.nil?

          where = Object.const_source_location(klass.name)
          where.nil? ? nil : above(*where)
        end

        # The comment above one method of a class, or nil.
        def for_method(klass, name)
          where = klass.instance_method(name).source_location
          where.nil? ? nil : above(*where)
        end

        # The comment block ending just above `line` of `file`, or nil.
        def above(file, line)
          lines = source(file)
          return nil if lines.empty?

          # Skip the declaration lines above the `def`; a blank line ends the walk, so the
          # comment must sit directly above.
          at = line - 2
          at -= 1 while at >= 0 && !lines[at].match?(COMMENT) &&
                        !lines[at].strip.empty? && !lines[at].match?(ENDS_WHAT_CAME_BEFORE)
          block = []
          while at >= 0 && (said = lines[at].match(COMMENT))
            block.unshift(said[2].rstrip)
            at -= 1
          end
          one_line(block)
        end

        # A comment as the model reads it: one line, its blank lines dropped, ending at the first
        # tag line (`@param`). Word for word what the TypeScript package does to a JSDoc.
        def one_line(block)
          said = block.map(&:strip).take_while { |line| !line.start_with?("@") }.reject(&:empty?)
          said.empty? ? nil : said.join(" ")
        end

        # Cached per process so a running agent never reads the disk between turns.
        def source(file)
          @source ||= {}
          @source[file] ||= File.exist?(file) ? File.readlines(file, chomp: true) : []
        end

        # Clear the cache; for tests that rewrite and reload a file.
        def forget = @source = {}
      end
    end
  end
end
