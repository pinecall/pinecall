# frozen_string_literal: true

require "test_helper"

# What the serve entry is told: a file with the slug at its place, a state field by field, no flag of its own.
class LoadingTest < Minitest::Test
  Loading = Pinecall::Serve::Loading

  def test_each_file_is_paired_with_the_slug_at_its_place
    flags = Loading.parse(%w[--file a.rb --slug a --file b.rb --slug b --console --events])

    assert_equal [%w[a.rb a], %w[b.rb b]], flags.served.map { |one| [one.file, one.slug] }
    assert flags.console
    assert flags.events
  end

  def test_a_file_without_its_slug_is_refused
    error = assert_raises(Pinecall::Serve::CannotServe) { Loading.parse(%w[--file a.rb]) }
    assert_includes error.message, "one --slug for each --file"
  end

  def test_a_state_is_read_field_by_field_as_json_and_a_value_that_is_not_json_is_refused
    flags = Loading.parse(["--file", "a.rb", "--slug", "a", "--state", 'patient={"name":"Ana"}', "--state", "slots=[]"])

    assert_equal({ patient: { name: "Ana" }, slots: [] }, flags.state)
    error = assert_raises(Pinecall::Serve::CannotServe) { Loading.as_state("patient={nope") }
    assert_equal "--state patient: its value is not JSON", error.message
  end

  def test_a_flag_it_does_not_have_is_refused_by_name
    error = assert_raises(Pinecall::Serve::CannotServe) { Loading.parse(%w[--file a.rb --slug a --fast]) }
    assert_equal "serve has no flag --fast", error.message
  end
end
