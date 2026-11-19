# frozen_string_literal: true

require "test_helper"

# The judges a class owns and the callers its test folder holds: each built or refused by sentence, the roster a
# `test/personas.rb` holds, and the class's own for one that still names its callers.
class HarnessTest < Minitest::Test
  Harness = Pinecall::Agent::Harness

  OFFERS = Pinecall.own_judge(name: "offers-next-slot", asks: "Did the agent offer the next free slot before the caller asked twice?",
                              reads: ["facts"])

  RUSH = Pinecall.own_persona(name: "in-a-rush", goal: "book today", style: "short, interrupts",
                              expects: ["The agent should offer today."], behavior: { interrupts: 0.3, pause_s: 1 })

  # Owns its judges and its personas.
  class Owns < Pinecall::Agent
    judges on: %w[consent grounded], own: [OFFERS]
    personas on: %w[in-a-hurry], own: [RUSH]
  end

  # Declares neither.
  class Silent < Pinecall::Agent
  end

  # Its callers are its test folder's.
  class Tested < Pinecall::Agent
  end

  # What a `test/personas.rb` leaves in the module it was loaded in.
  def held(source)
    Module.new.tap { |held| held.module_eval(source, "/agents/front-desk/test/personas.rb", 1) }
  end

  # None but Pinecall's.
  class Bare < Pinecall::Agent
    judges on: []
  end

  def test_a_judge_of_the_agents_own_is_its_question_with_how_and_when_filled_in
    assert_equal({ name: "offers-next-slot", question: "Did the agent offer the next free slot before the caller asked twice?",
                   answer: "verdict", choices: [], when: "always", trigger: "", reads: ["facts"] }, OFFERS)
  end

  def test_a_judge_answers_one_of_several_on_a_trigger_reading_what_it_was_told_to
    read = Pinecall.own_judge(name: "reason", asks: "Why did they call?", answer: "choice", choices: %w[book cancel],
                              when: "trigger", trigger: "Did the caller say why?", reads: %w[prompt evidence])

    assert_equal ["choice", %w[book cancel], "trigger", "Did the caller say why?", %w[prompt evidence]],
                 [read[:answer], read[:choices], read[:when], read[:trigger], read[:reads]]
  end

  REFUSED_JUDGES = [
    [{ name: "offers", asks: " " }, "offers: a judge asks a question of a call: write it as asks"],
    [{ name: "offers", asks: "Q?", answer: "maybe" }, 'offers: answer is "maybe", not one of verdict, choice, score'],
    [{ name: "offers", asks: "Q?", answer: "choice", choices: ["a"] }, "offers: a judge that answers one of several needs at least two choices"],
    [{ name: "offers", asks: "Q?", choices: %w[a b] }, "offers: only a judge that answers one of several takes choices"],
    [{ name: "offers", asks: "Q?", when: "trigger" }, "offers: a judge that runs on a trigger needs the trigger's question"],
    [{ name: "offers", asks: "Q?", reads: ["dreams"] }, 'offers: reads is "dreams", not one of prompt, evidence, facts'],
    [{ name: "Offers Slot", asks: "Q?" }, "\"Offers Slot\" is not a judge's name: lower-case words joined by hyphens"],
    [{ name: "offers", asks: "Q?", mood: "x" }, "a judge takes no mood"]
  ].freeze

  def test_a_judge_that_is_wrong_is_refused_by_sentence
    REFUSED_JUDGES.each do |given, sentence|
      error = assert_raises(Pinecall::DeclarationRefused, given.inspect) { Pinecall.own_judge(**given) }
      assert_includes error.message, sentence
    end
  end

  def test_a_persona_of_the_agents_own_is_what_a_put_takes_under_its_name
    assert_equal ["in-a-rush", "book today", ["The agent should offer today."]], [RUSH[:name], RUSH[:goal], RUSH[:expects]]
    assert_equal({ interrupts: 0.3, pause_s: 1 }, RUSH[:behavior])
  end

  REFUSED_PERSONAS = [
    [{ name: "in-a-rush", goal: " ", style: "s" }, "in-a-rush: a persona wants something: write its goal, in the first person"],
    [{ name: "in-a-rush", goal: "g", style: "" }, "in-a-rush: a persona talks some way: write its style"],
    [{ name: "in-a-rush", goal: "g", style: "s", mood: "x" }, "mood"],
    [{ name: "In A Rush", goal: "g", style: "s" }, "\"In A Rush\" is not a persona's name"]
  ].freeze

  def test_a_persona_that_is_wrong_is_refused_by_sentence
    REFUSED_PERSONAS.each do |given, sentence|
      error = assert_raises(Pinecall::DeclarationRefused, given.inspect) { Pinecall.own_persona(**given) }
      assert_includes error.message, sentence
    end
  end

  def test_what_the_class_owns_is_its_switches_plus_its_own_as_the_declaration_sends_it
    declared = Harness.declared(Owns)

    assert_equal({ on: %w[consent grounded], own: [OFFERS] }, declared[:judges])
    assert_equal({ on: ["in-a-hurry"], own: [RUSH] }, declared[:personas])
    sent = Owns.wire_config(tools: [])
    assert_equal declared[:judges], sent[:judges]
    Pinecall::Wire::Validate.call!("AgentConfig", sent, where: "configure")
  end

  def test_a_class_that_declares_neither_leaves_both_to_the_org
    assert_empty Harness.declared(Silent)
    refute Silent.wire_config(tools: []).key?(:judges)
  end

  def test_a_class_that_declares_them_with_none_of_its_own_owns_an_empty_list_and_its_switches
    sent = Bare.wire_config(tools: [])

    assert_equal({ on: [], own: [] }, sent[:judges])
    refute sent.key?(:personas)
  end

  def test_a_persona_is_told_as_one_own_persona_made_and_is_sent_as_the_plain_object_it_was
    plain = { name: "in-a-rush", goal: "book today", style: "short, interrupts" }
    made = Pinecall.own_persona(**plain)

    assert_kind_of Harness::OwnPersona, made
    assert_equal plain, made
    assert_equal JSON.generate(plain), JSON.generate(made)
    assert_instance_of Hash, Pinecall::Wire::Codec.plain(made)
  end

  def test_the_roster_of_a_file_is_every_own_persona_it_defines_in_the_order_written_and_on_for_pinecalls
    file = held(<<~RUBY)
      ZEALOUS = Pinecall.own_persona(name: "zealous", goal: "book today", style: "short")
      ON = %w[in-a-hurry wrong-number].freeze
      NOT_A_CALLER = { name: "plain", goal: "g", style: "s" }.freeze
      HOW_MANY = 2
      ANGRY = Pinecall.own_persona(name: "angry", goal: "one charge back", style: "annoyed")
    RUBY
    roster = Harness.roster_in(file, "test/personas.rb")

    assert_equal %w[in-a-hurry wrong-number], roster[:on]
    assert_equal %w[zealous angry], roster[:own].map { |one| one[:name] }
    Pinecall::Wire::Validate.call!("PersonasDeclared", roster, where: "personas")
  end

  def test_a_file_with_no_on_plays_none_of_pinecalls_and_one_with_no_caller_owns_none
    assert_equal({ on: [], own: [RUSH] }, Harness.roster_in(Module.new.tap { |held| held.const_set(:RUSH, RUSH) }, "test/personas.rb"))
    assert_equal({ on: ["in-a-hurry"], own: [] }, Harness.roster_in(held("ON = %w[in-a-hurry]\n"), "test/personas.rb"))
    assert_equal({ on: [], own: [] }, Harness.roster_in(Module.new, "test/personas.rb"))
  end

  def test_an_on_that_is_not_an_array_of_strings_and_two_callers_of_one_name_are_refused_by_sentence
    ["ON = \"in-a-hurry\"\n", "ON = [:in_a_hurry]\n", "ON = nil\n"].each do |source|
      error = assert_raises(Pinecall::DeclarationRefused, source) { Harness.roster_in(held(source), "/agents/x/test/personas.rb") }
      assert_equal "/agents/x/test/personas.rb: ON is the names of Pinecall's callers the agent is tested with, an array of strings", error.message
    end
    twice = held(<<~RUBY)
      ONE = Pinecall.own_persona(name: "hurried", goal: "g", style: "s")
      OTHER = Pinecall.own_persona(name: "hurried", goal: "another", style: "s")
    RUBY
    error = assert_raises(Pinecall::DeclarationRefused) { Harness.roster_in(twice, "test/personas.rb") }
    assert_includes error.message, "two personas called hurried: a name is declared once"
  end

  def test_the_roster_of_its_file_is_what_the_class_sends_as_its_personas
    roster = Harness.roster_in(held("ON = %w[in-a-hurry]\nRUSH = Pinecall.own_persona(name: \"in-a-rush\", goal: \"book today\", style: \"short\")\n"),
                               "test/personas.rb")
    Harness.tested_with(Tested, roster, "test/personas.rb")
    sent = Tested.wire_config(tools: [])

    assert_equal({ on: ["in-a-hurry"], own: [{ name: "in-a-rush", goal: "book today", style: "short" }] }, sent[:personas])
    assert_equal sent[:personas], Harness.declared(Tested)[:personas]
    refute Harness.names_its_callers?(Tested)
    refute sent.key?(:judges)
    Pinecall::Wire::Validate.call!("AgentConfig", sent, where: "configure")
    assert_nil Class.new(Tested).tested_with, "a roster is one class's, never its subclass's"
  end

  def test_a_class_that_names_its_personas_and_has_the_file_too_is_refused_and_keeps_its_own
    assert Harness.names_its_callers?(Owns)
    error = assert_raises(Pinecall::DeclarationRefused) do
      Harness.tested_with(Owns, { on: [], own: [] }, "/agents/owns/test/personas.rb")
    end

    assert_equal "HarnessTest::Owns declares personas in the class and /agents/owns/test/personas.rb holds them too: " \
                 "the file is their place — take personas out of the class", error.message
    assert_nil Owns.tested_with
    assert_equal({ on: ["in-a-hurry"], own: [RUSH] }, Harness.declared(Owns)[:personas])
  end

  def test_two_of_one_name_and_an_own_written_as_a_plain_hash_that_is_wrong_are_refused
    twice = Class.new(Pinecall::Agent) { judges on: [], own: [OFFERS, OFFERS] }
    error = assert_raises(Pinecall::DeclarationRefused) { Harness.declared(twice) }
    assert_includes error.message, "two judges called offers-next-slot: a name is declared once"
    wrong = Class.new(Pinecall::Agent) { judges on: [], own: [OFFERS.merge(answer: "maybe")] }
    error = assert_raises(Pinecall::DeclarationRefused) { Harness.declared(wrong) }
    assert_includes error.message, "offers-next-slot:"
    nameless = Class.new(Pinecall::Agent) { personas on: [], own: [{ goal: "g", style: "s" }] }
    assert_raises(ArgumentError) { Harness.declared(nameless) }
  end
end
