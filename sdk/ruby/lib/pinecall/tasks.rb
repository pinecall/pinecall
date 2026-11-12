# frozen_string_literal: true

module Pinecall
  # One thing a tool needs from the caller before it can finish, asked for in the middle of the tool.
  # `check` takes what the model gave (a Hash of strings) and answers what the tool is handed.
  Task = Data.define(:name, :asks, :fields, :check, :how)

  # Tasks: making one, the tool it is given with, and what the model is told when a tool asks.
  module Tasks
    A_NAME = /\A[a-z][a-z0-9_]*\z/
    GIVE = "give_"
    AN_EMAIL = /\A[^\s@]+@[^\s@]+\.[^\s@]{2,}\z/
    DIGITS = (7..15)

    module_function

    # A task of your own: `Pinecall.task("plate", asks: "the plate", fields: { plate: "…" }) { |given| … }`.
    def task(name, asks:, fields:, how: nil, &check)
      name = name.to_s
      unless A_NAME.match?(name)
        raise DeclarationRefused, "a task's name is lowercase letters, digits and underscores: it names the tool the model gives it with"
      end
      raise DeclarationRefused, "the task #{name} says what it asks for: asks: \"the caller's email address\"" if asks.to_s.strip.empty?
      raise DeclarationRefused, "the task #{name} names what the model gives: fields: { email: \"the address\" }" if fields.empty?
      raise DeclarationRefused, "the task #{name} has a check: a block of what the model gave" if check.nil?

      Task.new(name:, asks:, fields: fields.transform_keys(&:to_s).freeze, check:, how:)
    end

    # The name of the tool a task is given with.
    def given_with(asked) = "#{GIVE}#{asked.name}"

    # The tool a task is given with, as it is declared.
    def giving_tool(asked)
      {
        name: given_with(asked),
        description: "Give #{asked.asks}, once the caller gave it to you. Never guess it and never make one up.",
        parameters: {
          type: "object",
          properties: asked.fields.to_h { |name, what| [name.to_sym, { type: "string", description: what }] },
          required: asked.fields.keys
        },
        side_effect: "read"
      }
    end

    # What the model is told when a tool stops to ask.
    def asking_for(asked)
      how = asked.how.nil? ? "" : " #{asked.how}"
      "This is not done yet: it needs #{asked.asks}. Ask the caller for it now.#{how} Then call #{given_with(asked)}."
    end

    def email(given)
      address = given["email"].to_s.strip.downcase
      raise ArgumentError, "\"#{given["email"]}\" is not an email address. Ask them to say it again, slowly." unless AN_EMAIL.match?(address)

      address
    end

    def phone(given)
      number = given["number"].to_s
      digits = number.gsub(/\D/, "")
      raise ArgumentError, "\"#{number}\" is not a phone number. Ask for it again, digit by digit." unless DIGITS.cover?(digits.length)

      number.strip.start_with?("+") ? "+#{digits}" : digits
    end

    def full_name(given)
      first, last = given.values_at("first", "last").map { |part| part.to_s.strip }
      raise ArgumentError, "Both names are needed. Ask for the one that is missing." if first.empty? || last.empty?

      { first:, last: }
    end
  end

  # The caller's email address, lowercased.
  GetEmail = Tasks.task("email", asks: "the caller's email address",
                                 how: "Spell it back to them letter by letter and wait for a yes.",
                                 fields: { email: "The address as it is typed, like ana@example.com: no spaces, no words like 'at' or 'dot'." }) do |given|
    Tasks.email(given)
  end

  # The caller's phone number, digits only, with its `+` when they gave a country code.
  GetPhone = Tasks.task("phone", asks: "a phone number to reach the caller at",
                                 how: "Read it back in groups of digits and wait for a yes.",
                                 fields: { number: "The number in digits, with its country code when they said one: +14155550142." }) do |given|
    Tasks.phone(given)
  end

  # The caller's first and last name.
  GetName = Tasks.task("name", asks: "the caller's first and last name",
                               how: "Ask how the last name is spelled when it is not a common one.",
                               fields: { first: "Their first name.", last: "Their last name." }) do |given|
    Tasks.full_name(given)
  end
end
