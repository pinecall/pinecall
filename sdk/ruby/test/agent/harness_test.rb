# frozen_string_literal: true

require "test_helper"
require "tmpdir"

# The judges and the personas a class owns: the switches, the files beside it read, and each refusal as a sentence.
class HarnessTest < Minitest::Test
  Harness = Pinecall::Agent::Harness

  OFFERS = <<~JUDGE
    ---
    answer: verdict
    when: always
    reads: [facts]
    ---
    Did the agent offer the next free slot before the caller asked twice?
  JUDGE

  RUSH = JSON.generate(goal: "book today", style: "short, interrupts", expects: ["The agent should offer today."],
                       behavior: { interrupts: 0.3, pause_s: 1 })

  # Owns its judges and its personas.
  class Owns < Pinecall::Agent
    judges on: %w[consent grounded]
    personas on: %w[in-a-hurry]
  end

  # Declares neither.
  class Silent < Pinecall::Agent
  end

  # None but Pinecall's.
  class Bare < Pinecall::Agent
    judges on: []
  end

  # A folder shaped like `agents/<slug>/`, with the files given under `judges/` and `test/personas/`.
  def folder(files)
    dir = Dir.mktmpdir("harness")
    files.each do |path, text|
      FileUtils.mkdir_p(File.dirname(File.join(dir, path)))
      File.write(File.join(dir, path), text)
    end
    dir
  end

  def test_a_judge_file_is_read_as_the_library_writes_one
    read = Harness.judge_of("judges/offers-next-slot.md", OFFERS)

    assert_equal({ name: "offers-next-slot", question: "Did the agent offer the next free slot before the caller asked twice?",
                   answer: "verdict", choices: [], when: "always", trigger: "", reads: ["facts"] }, read)
  end

  def test_a_judge_file_takes_the_librarys_on_for_when_and_a_comma_separated_list
    read = Harness.judge_of("x.md", "---\non: simulations\nreads: prompt, evidence\n---\nWas it kind?")

    assert_equal ["simulations", %w[prompt evidence]], [read[:when], read[:reads]]
  end

  REFUSED_JUDGES = [
    ["offers.md", "no front matter\n", "a judge opens with its front matter between two --- lines"],
    ["offers.md", "---\n\n---\n\n", "a judge asks a question of a call: write one below the front matter"],
    ["offers.md", "---\nanswer: maybe\n---\nQ?", 'answer is "maybe", not one of verdict, choice, score'],
    ["offers.md", "---\nanswer: choice\nchoices: [a]\n---\nQ?", "needs at least two choices"],
    ["offers.md", "---\nchoices: [a, b]\n---\nQ?", "only a judge that answers one of several takes choices"],
    ["offers.md", "---\nwhen: trigger\n---\nQ?", "a judge that runs on a trigger needs the trigger's question"],
    ["offers.md", "---\nreads: dreams\n---\nQ?", 'reads is "dreams", not one of prompt, evidence, facts'],
    ["Offers Slot.md", "---\n\n---\nQ?", "\"Offers Slot\" is not a judge's name: lower-case words joined by hyphens"],
    ["offers.md", "---\nname: other\n---\nQ?", "its front matter says name: other, and the file is offers.md"]
  ].freeze

  def test_a_judge_file_that_is_wrong_is_refused_by_sentence
    REFUSED_JUDGES.each do |file, text, sentence|
      error = assert_raises(Pinecall::DeclarationRefused, file) { Harness.judge_of(file, text) }
      assert_includes error.message, sentence
    end
  end

  def test_a_persona_file_is_what_a_put_takes_under_the_files_name
    read = Harness.persona_of("test/personas/in-a-rush.json", RUSH)

    assert_equal ["in-a-rush", "book today", ["The agent should offer today."]], [read[:name], read[:goal], read[:expects]]
    assert_equal({ interrupts: 0.3, pause_s: 1 }, read[:behavior])
  end

  REFUSED_PERSONAS = [
    ["in-a-rush.json", "{", "not JSON"],
    ["in-a-rush.json", "[]", "a persona is a JSON object with a goal and a style"],
    ["in-a-rush.json", '{"style": "s"}', "a persona wants something: write its goal, in the first person"],
    ["in-a-rush.json", '{"goal": "g"}', "a persona talks some way: write its style"],
    ["in-a-rush.json", '{"goal": "g", "style": "s", "name": "other"}', "it says its name is other"],
    ["in-a-rush.json", '{"goal": "g", "style": "s", "mood": "x"}', "mood"],
    ["In A Rush.json", "{}", "\"In A Rush\" is not a persona's name"]
  ].freeze

  def test_a_persona_file_that_is_wrong_is_refused_by_sentence
    REFUSED_PERSONAS.each do |file, text, sentence|
      error = assert_raises(Pinecall::DeclarationRefused, file) { Harness.persona_of(file, text) }
      assert_includes error.message, sentence
    end
  end

  def test_what_the_class_owns_is_its_switches_plus_the_folders_beside_it
    dir = folder("judges/offers-next-slot.md" => OFFERS, "test/personas/in-a-rush.json" => RUSH)
    declared = Harness.declared(Owns, folder: dir)

    assert_equal %w[consent grounded], declared[:judges][:on]
    assert_equal ["offers-next-slot"], declared[:judges][:own].map { |one| one[:name] }
    assert_equal({ on: ["in-a-hurry"] }, declared[:personas].slice(:on))
    assert_equal ["in-a-rush"], declared[:personas][:own].map { |one| one[:name] }
  end

  def test_a_class_that_declares_nothing_with_no_folder_leaves_both_to_the_org
    assert_empty Harness.declared(Silent, folder: folder({}))
    assert_empty Harness.declared(Silent, folder: nil)
    refute Silent.wire_config(tools: []).key?(:judges)
  end

  def test_a_class_that_declares_them_with_no_folder_owns_an_empty_list_and_its_switches
    sent = Bare.wire_config(tools: [])

    assert_equal({ on: [], own: [] }, sent[:judges])
    refute sent.key?(:personas)
    Pinecall::Wire::Validate.call!("AgentConfig", sent, where: "configure")
  end

  def test_a_folder_with_files_the_class_never_declared_is_refused_saying_what_to_write
    with_judges = folder("judges/offers-next-slot.md" => OFFERS)
    error = assert_raises(Pinecall::DeclarationRefused) { Harness.declared(Silent, folder: with_judges) }
    assert_includes error.message, 'holds 1 judge(s) and the class declares none: judges on: ["consent", …]'
    with_personas = folder("test/personas/in-a-rush.json" => RUSH)
    error = assert_raises(Pinecall::DeclarationRefused) { Harness.declared(Silent, folder: with_personas) }
    assert_includes error.message, "holds 1 persona(s) and the class declares none"
  end
end
