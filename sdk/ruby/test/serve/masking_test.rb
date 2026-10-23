# frozen_string_literal: true

require "test_helper"

# What a served process prints: the values its agent declared private, masked as the call's log masks them.
class MaskingTest < Minitest::Test
  DECLARED = {
    tools: [{ name: "take_message", description: "d", parameters: {}, pii: %w[name] }],
    state_fields: [{ name: "patient", visibility: "pii" }, { name: "stage", visibility: "tenant" }]
  }.freeze

  def entry(type, data) = Pinecall::Wire::Entry.new(seq: 3, ts: 1.0, call: "CA_1", agent: "desk", type:, ephemeral: false, data:)

  def asked(arguments = { name: "Ana Lopez", about: "Ana Lopez wants a refund" })
    entry("tool.call", { call_id: "tc_1", name: "take_message", arguments: })
  end

  def masking = Pinecall::Serve::Masking.new(DECLARED)

  def test_the_argument_a_tool_names_is_masked_and_so_is_the_value_wherever_another_argument_repeats_it
    shown = masking.entry(asked)

    assert_equal({ name: "***", about: "*** wants a refund" }, shown.data[:arguments])
  end

  def test_the_value_is_masked_in_the_state_that_holds_it_in_what_the_tool_answered_and_in_a_logged_line
    masking = self.masking
    masking.entry(asked)
    state = masking.entry(entry("state.changed", { state: { message: { name: "Ana Lopez" }, stage: "done" }, changed: [] }))
    answer = masking.entry(entry("tool.result", { call_id: "tc_1", name: "take_message", output: "Saved for Ana Lopez." }))
    logged = masking.entry(entry("custom", { name: "booked", data: { who: "Ana Lopez" } }))

    assert_equal({ message: { name: "***" }, stage: "done" }, state.data[:state])
    assert_equal "Saved for ***.", answer.data[:output]
    assert_equal({ who: "***" }, logged.data[:data])
  end

  def test_a_state_field_declared_private_is_masked_whole_before_any_tool_call
    shown = masking.entry(entry("state.changed", { state: { patient: { id: 7 }, stage: "ask" }, changed: ["patient"] }))

    assert_equal({ patient: "***", stage: "ask" }, shown.data[:state])
  end

  def test_what_was_said_is_left_alone_and_an_entry_with_nothing_private_is_the_entry_itself
    masking = self.masking
    masking.entry(asked)
    said = entry("turn.user", { speech_id: "s1", text: "Soy Ana Lopez" })
    quiet = entry("state.changed", { state: { stage: "ask" }, changed: ["stage"] })

    assert_same said, masking.entry(said)
    assert_equal({ stage: "ask" }, masking.entry(quiet).data[:state])
    nothing_declared = asked
    assert_same nothing_declared, Pinecall::Serve::Masking.new({}).entry(nothing_declared)
  end

  def test_a_value_is_masked_only_as_a_whole_token
    masking = self.masking
    masking.entry(asked({ name: "Ana", about: "x" }))
    said = masking.entry(entry("custom", { name: "n", data: { a: "Ana called, Anabel and Banana did not, Ana." } }))

    assert_equal "*** called, Anabel and Banana did not, ***.", said.data[:data][:a]
  end

  def test_a_number_inside_a_longer_number_is_not_the_value
    masking = self.masking
    masking.entry(asked({ name: 600_123_456, about: "x" }))
    shown = masking.entry(entry("custom", { name: "n", data: { phone: 600_123_456, other: 6_001_234_567, text: "call 600123456 now" } }))

    assert_equal({ phone: "***", other: 6_001_234_567, text: "call *** now" }, shown.data[:data])
  end

  def test_a_value_shorter_than_three_characters_is_masked_by_name_and_never_by_value
    masking = self.masking
    asked_short = masking.entry(asked({ name: "Al", about: "Al is here, at 7" }))
    shown = masking.entry(entry("custom", { name: "n", data: { who: "Al", at: 7 } }))

    assert_equal({ name: "***", about: "Al is here, at 7" }, asked_short.data[:arguments])
    assert_equal({ who: "Al", at: 7 }, shown.data[:data])
  end

  def test_a_blank_value_masks_nothing
    masking = self.masking
    masking.entry(asked({ name: "   ", about: "x y z" }))

    assert_equal "x y z", masking.entry(entry("custom", { name: "n", data: { a: "x y z" } })).data[:data][:a]
  end

  def test_what_one_agent_learned_is_not_another_s
    masking = self.masking
    masking.entry(asked)
    other = Pinecall::Serve::Masking.new(DECLARED)

    assert_equal "Ana Lopez", other.entry(entry("tool.result", { call_id: "x", name: "take_message", output: "Ana Lopez" })).data[:output]
  end
end
