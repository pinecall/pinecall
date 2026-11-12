# frozen_string_literal: true

require "test_helper"

# A task: what a tool asks the caller for mid-tool, given back with a tool of its own.
class TasksTest < Minitest::Test
  def test_a_task_is_refused_without_a_name_a_question_fields_or_a_check
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.task("Plate", asks: "the plate", fields: { plate: "it" }) { |given| given } }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.task("plate", asks: " ", fields: { plate: "it" }) { |given| given } }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.task("plate", asks: "the plate", fields: {}) { |given| given } }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.task("plate", asks: "the plate", fields: { plate: "it" }) }
  end

  def test_a_task_is_given_with_a_tool_named_after_it_that_takes_its_fields_as_words
    spec = Pinecall::Tasks.giving_tool(Pinecall::GetName)

    assert_equal "give_name", spec[:name]
    assert_equal %w[first last], spec[:parameters][:required]
    assert_includes spec[:description], "Never guess it"
  end

  def test_the_model_is_told_what_is_missing_how_to_ask_and_which_tool_gives_it
    said = Pinecall::Tasks.asking_for(Pinecall::GetEmail)

    assert_includes said, "it needs the caller's email address"
    assert_includes said, "letter by letter"
    assert said.end_with?("Then call give_email.")
  end

  def test_the_built_in_tasks_hand_the_tool_a_clean_value_and_refuse_a_wrong_one
    assert_equal "ana@example.com", Pinecall::GetEmail.check.call({ "email" => " Ana@Example.COM " })
    assert_equal "+14155550142", Pinecall::GetPhone.check.call({ "number" => "+1 (415) 555-0142" })
    assert_equal({ first: "Ana", last: "Ruiz" }, Pinecall::GetName.check.call({ "first" => " Ana ", "last" => "Ruiz" }))
    assert_raises(ArgumentError) { Pinecall::GetEmail.check.call({ "email" => "ana at example" }) }
    assert_raises(ArgumentError) { Pinecall::GetPhone.check.call({ "number" => "12" }) }
  end
end
