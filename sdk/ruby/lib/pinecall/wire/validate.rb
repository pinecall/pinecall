# frozen_string_literal: true

# Checks a value against a named shape of the table, field by field, refusing a key nobody declared.

module Pinecall
  module Wire
    # Validates a payload against the generated shape tables and names the offending field.
    # The Ruby counterpart of zod and pydantic; a table walk avoids a schema-library dependency.
    module Validate
      module_function

      # Validate a payload against the named shape and return it. Shapes are closed: an undeclared
      # key (e.g. from a newer protocol) is refused rather than silently dropped.
      def call!(name, value, where: name)
        return union!(name, value, where) if Shapes::UNIONS.key?(name)
        return map!(Shapes::MAPS.fetch(name), value, where) if Shapes::MAPS.key?(name)

        shape = Shapes::SHAPES[name]
        raise WireError, "#{where}: the protocol declares no shape called #{name}" if shape.nil?
        raise WireError, "#{where}: expected the fields of #{name}, got #{named(value)}" unless value.is_a?(Hash)

        unknown = value.keys - shape.keys
        raise WireError, "#{where}: #{name} has no field called #{unknown.join(", ")}" unless unknown.empty?

        shape.each { |field, spec| field_of!(shape: name, spec:, value:, field:, where:) }
        value
      end

      # One field. An optional one may be absent or null, as TypeScript's nullish reads it: the
      # runtime writes null for a field it set to nothing.
      def field_of!(shape:, spec:, value:, field:, where:)
        return if !spec[:required] && value[field].nil?
        raise WireError, "#{where}.#{field}: #{shape} requires it" unless value.key?(field)

        field!(spec, value[field], "#{where}.#{field}")
      end

      # One value against a field descriptor; one branch per kind the generator emits.
      def field!(spec, value, where)
        if value.nil?
          return if spec[:null]

          raise WireError, "#{where}: nothing is not one of the things it may be"
        end

        case spec[:kind]
        when :str then string!(spec, value, where)
        when :int then expect(value, Integer, where, "a whole number")
        when :float then expect(value, Numeric, where, "a number")
        when :bool then expect_boolean(value, where)
        when :json then expect(value, Hash, where, "an object")
        when :any then value
        when :list then list!(spec, value, where)
        when :tuple then tuple!(spec, value, where)
        when :map then map!(spec[:items], value, where)
        when :enum then one_of!(spec[:values], value, where)
        when :const then const!(spec[:const], value, where)
        when :ref then ref!(spec[:ref], value, where)
        else raise WireError, "#{where}: the generator emitted a kind nobody reads: #{spec[:kind]}"
        end
      end

      # A union is told apart by the one field the schema's discriminator names.
      def union!(name, value, where)
        union = Shapes::UNIONS.fetch(name)
        on = union[:on]
        said = value.is_a?(Hash) ? value[on] : nil
        member = union[:members].find { |one| Shapes::SHAPES.dig(one, on, :const) == said }
        if member.nil?
          allowed = union[:members].filter_map { |one| Shapes::SHAPES.dig(one, on, :const) }
          raise WireError, "#{where}: #{on} #{said.inspect} is not one of #{allowed.join(", ")}"
        end
        call!(member, value, where:)
      end

      # A reference points at another object, at a union, or at one of the closed lists.
      def ref!(name, value, where)
        allowed = Enums::ALL[name]
        return one_of!(allowed, value, where) unless allowed.nil?

        call!(name, value, where:)
      end

      def list!(spec, value, where)
        expect(value, Array, where, "a list")
        value.each_with_index { |item, at| field!(spec[:items], item, "#{where}[#{at}]") }
      end

      # A tuple has a fixed length and one shape per position, e.g. a transcript line [who, what].
      def tuple!(spec, value, where)
        expect(value, Array, where, "a list")
        places = spec[:members]
        unless value.length == places.length
          raise WireError, "#{where}: a list of #{places.length} things, not #{value.length}"
        end

        places.each_with_index { |place, at| field!(place, value[at], "#{where}[#{at}]") }
      end

      # Map keys are app-chosen names; every value has the same shape.
      def map!(spec, value, where)
        expect(value, Hash, where, "an object")
        value.each { |key, item| field!(spec, item, "#{where}.#{key}") }
      end

      # JSON Schema's ^ and $ anchor the whole string but Ruby's anchor a line, so a value with a
      # newline is refused before matching.
      def string!(spec, value, where)
        expect(value, String, where, "a string")
        pattern = spec[:pattern]
        return value if pattern.nil? || (!value.include?("\n") && Regexp.new(pattern).match?(value))

        raise WireError, "#{where}: #{value.inspect} does not match #{pattern}"
      end

      def one_of!(values, value, where)
        return value if values.include?(value)

        raise WireError, "#{where}: #{value.inspect} is not one of #{values.join(", ")}"
      end

      def const!(const, value, where)
        return value if value == const

        raise WireError, "#{where}: this field is always #{const.inspect}, never #{value.inspect}"
      end

      def expect(value, type, where, called)
        return value if value.is_a?(type)

        raise WireError, "#{where}: expected #{called}, got #{named(value)}"
      end

      def expect_boolean(value, where)
        return value if value == true || value == false

        raise WireError, "#{where}: expected true or false, got #{named(value)}"
      end

      # Describe a value's type in the words the error messages use.
      def named(value)
        case value
        when nil then "nothing"
        when String then "a string"
        when Integer, Float then "a number"
        when true, false then "true or false"
        when Array then "a list"
        when Hash then "an object"
        else value.class.name
        end
      end
    end
  end
end
