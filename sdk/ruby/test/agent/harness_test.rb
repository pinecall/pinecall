# frozen_string_literal: true

require "test_helper"

# The judges and the personas a class owns: each built or refused by sentence, and the class's `own` sent as declared.
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
