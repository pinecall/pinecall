# frozen_string_literal: true

require "test_helper"

# Class config, and what `agent.configure` sends: the contract and the environment the class declares.
class ConfigTest < Minitest::Test
  # Un agente que sólo dice su contrato.
  class Clinica < Pinecall::Agent
    phone "+34910000000"
    web true
  end

  # Recepción que fija su voz, su modelo, sus oídos, su idioma y cómo abre.
  class Fijada < Pinecall::Agent
    voice "cartesia", "a0e99841-438c-4a64-b679-ae501e7d6091", model: "sonic-2"
    llm "openai/gpt-5.4-mini", temperature: 0.3, builds: "responses.LLM", options: { use_websocket: true }
    stt "soniox/stt-rt-v3", end_of_turn: :smart_turn
    judge "openai/qwen3-32b", options: { base_url: "http://gpu:8000/v1" }
    language "es"
    greeting "Clínica Norte, buenas."
    hangup "the caller says goodbye"
    says [{ word: "GSA", spoken: "ge ese a" }]
    hears "Vidal", "Sanitas"
    memory remember: ["alergias"], forget: ["pagos"]
    record false
  end

  def test_a_class_that_declares_no_environment_sends_its_contract_alone
    sent = Clinica.wire_config(tools: [])

    assert_equal %i[prompt tools], sent.keys
  end

  def test_the_doors_are_accepted_and_read_by_nobody
    assert_equal "+34910000000", Clinica.phone
    refute Clinica.wire_config(tools: []).key?(:routes)
    refute Clinica.respond_to?(:routes)
  end

  def test_the_whole_configuration_is_what_the_wire_declares
    Pinecall::Wire::Validate.call!("AgentConfig", Clinica.wire_config(tools: []), where: "configure")
    Pinecall::Wire::Validate.call!("AgentConfig", Fijada.wire_config(tools: []), where: "configure")
  end

  def test_what_the_class_declares_of_its_environment_is_sent_in_the_wires_shape
    sent = Fijada.wire_config(tools: [])

    assert_equal({ provider: "cartesia", voice_id: "a0e99841-438c-4a64-b679-ae501e7d6091", model: "sonic-2" }, sent[:voice])
    assert_equal({ provider: "openai", model: "gpt-5.4-mini", temperature: 0.3, builds: "responses.LLM",
                   options: { use_websocket: true } }, sent[:llm])
    assert_equal({ provider: "soniox", model: "stt-rt-v3", end_of_turn: "smart-turn" }, sent[:stt])
    assert_equal({ provider: "openai", model: "qwen3-32b", options: { base_url: "http://gpu:8000/v1" } }, sent[:judge])
    assert_equal "es", sent[:language]
    assert_equal({ say: "Clínica Norte, buenas." }, sent[:greeting])
    assert_equal({ when: "the caller says goodbye" }, sent[:hangup])
    assert_equal %w[Vidal Sanitas], sent[:hears]
    assert_equal({ remember: ["alergias"], forget: ["pagos"] }, sent[:memory])
    refute sent[:record]
    assert sent.key?(:record)
  end

  def test_a_subclass_inherits_what_its_parent_declared_and_may_change_it
    sub = Class.new(Fijada) { llm "anthropic/claude-haiku-5-5" }

    assert_equal({ provider: "anthropic", model: "claude-haiku-5-5" }, sub.llm)
    assert_equal "es", sub.language
    assert_equal({ provider: "openai", model: "gpt-5.4-mini", temperature: 0.3, builds: "responses.LLM",
                   options: { use_websocket: true } }, Fijada.llm)
  end

  def test_a_model_id_keeps_every_slash_after_the_vendors
    declared = Class.new(Pinecall::Agent) { llm "livekit/openai/gpt-5-mini" }

    assert_equal({ provider: "livekit", model: "openai/gpt-5-mini" }, declared.llm)
  end

  def test_a_voice_names_its_vendor_and_the_voice_or_is_refused_at_load
    refused = assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) { voice "carolina" }
    end

    assert_equal 'a voice the class declares names its vendor and the voice: voice "<vendor>", "<voice id>"', refused.message
  end

  def test_an_opening_is_words_said_or_the_models_own_with_or_without_an_instruction
    opening = ->(&body) { Class.new(Pinecall::Agent, &body).greeting }

    assert_equal({ reply: "" }, opening.call { greeting :improvise })
    assert_equal({ reply: "Saludá por el nombre" }, opening.call { greeting improvise("Saludá por el nombre") })
    assert_equal({ reply: "Saludá", allow_interruptions: true },
                 opening.call { greeting improvise("Saludá", interruptible: true) })
    assert_equal({ say: "Aviso legal…", allow_interruptions: false },
                 opening.call { greeting "Aviso legal…", interruptible: false })
    assert_raises(Pinecall::DeclarationRefused) { opening.call { greeting 42 } }
  end

  def test_hangup_is_when_in_words_or_true_for_whenever_the_model_judges
    assert_equal({ when: "" }, Class.new(Pinecall::Agent) { hangup true }.hangup)
    assert_raises(Pinecall::DeclarationRefused) { Class.new(Pinecall::Agent) { hangup "" } }
  end
end
