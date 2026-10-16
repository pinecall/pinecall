# frozen_string_literal: true

require "test_helper"

# The framework's own words in identity: English rules for any agent, and the channel's block.
class RulesTest < Minitest::Test
  # Agenda de la Clínica Norte.
  class Clinica < Pinecall::Agent; end

  # Agenda que escribe sus propias normas de formato.
  class SinCanal < Pinecall::Agent
    channel_rules false
  end

  SPOKEN = "You are on a phone call."
  WEBSITE = "You are in a written chat on a website."
  WHATSAPP = "You are on WhatsApp."

  # An agent serving a call on `channel`, with `medium` when the gateway said one.
  def serving(klass, channel, medium = nil)
    klass.new.seal.serving(Pinecall::CallWorld.new(id: "CA_1", contact: "", channel:, medium:) { |*| nil })
  end

  def identity_of(agent) = Pinecall.render(agent)[:identity]

  def channel_of(identity) = identity[%r{<channel>\n(.*?)\n</channel>}m, 1]

  def test_the_rules_are_english_for_every_agent_and_tell_it_to_answer_in_the_callers_language
    identity = identity_of(serving(Clinica, "phone"))

    assert_includes identity, "One question per turn"
    assert_includes identity, "- Answer in the language the caller speaks."
    assert_includes identity, "To act, call a tool"
    refute_includes identity, "Una sola pregunta"
  end

  def test_how_to_write_is_the_channel_blocks_not_a_rules
    rules = identity_of(Clinica.new.seal)[%r{<rules>\n(.*?)\n</rules>}m, 1]

    refute_includes rules, "markdown"
    refute_includes rules, "phone"
  end

  def test_each_channel_and_medium_says_how_to_write_there
    [["phone", "voice", SPOKEN], ["web", "voice", SPOKEN], ["web", "text", WEBSITE],
     ["whatsapp", "text", WHATSAPP], ["whatsapp", "voice", WHATSAPP]].each do |channel, medium, opening|
      assert channel_of(identity_of(serving(Clinica, channel, medium))).start_with?(opening), "#{channel} by #{medium}"
    end
  end

  def test_a_call_whose_gateway_does_not_say_takes_the_medium_its_channel_implies
    [["phone", SPOKEN], ["web", SPOKEN], ["whatsapp", WHATSAPP]].each do |channel, opening|
      assert channel_of(identity_of(serving(Clinica, channel))).start_with?(opening), channel
    end
  end

  def test_with_no_call_at_all_it_is_a_phone_calls
    assert channel_of(identity_of(Clinica.new.seal)).start_with?(SPOKEN)
  end

  def test_the_texts_are_the_ones_the_framework_ships_word_for_word
    assert_equal "You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, " \
                 "no lists, no bold, no symbols, no links. Say an email or a web address the way a person says it out loud.",
                 channel_of(identity_of(serving(Clinica, "phone")))
    assert_equal "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when there " \
                 "are steps, bold for the one thing that matters.",
                 channel_of(identity_of(serving(Clinica, "web", "text")))
    assert_equal "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, short messages.",
                 channel_of(identity_of(serving(Clinica, "whatsapp")))
  end

  def test_a_class_with_channel_rules_false_leaves_the_block_out_on_every_channel
    %w[phone web whatsapp].each do |channel|
      identity = identity_of(serving(SinCanal, channel))

      refute_includes identity, "<channel>"
      assert_includes identity, "<protocols>"
    end
  end

  def test_the_medium_stays_readable_on_the_call_when_the_block_is_off
    assert_equal "text", serving(SinCanal, "web", "text").call.medium
  end
end
