# frozen_string_literal: true

require "test_helper"

class PromptTest < Minitest::Test
  # Eres la recepción de Clínica Norte.
  # Todo lo que dices se lee en voz alta.
  class Clinica < Pinecall::Agent
    stage :identify, :book
    state :patient
    state :slots, []

    view template: <<~ERB
      <% if stage == :identify -%>
      Saluda y pide nombre y teléfono.
      <% end -%>
      <% if patient -%>
      Hablas con <%= patient %>.
      <% end -%>

      <% if remembers?("por la mañana") -%>
      Ofrécele primero las horas de la mañana.
      <% end -%>

      <% if slots.any? -%>
      ## Horas libres

      <% slots.each do |slot| -%>
      <%= slot %>
      <% end -%>
      <% end -%>

      <% if resumed -%>
      Se cortó su llamada anterior.
      <% end -%>
    ERB

    # Busca al paciente.
    tool stage: :identify
    def find_patient(name:)
      self.patient = name
      self.stage = :book
    end
  end

  def setup
    @agent = Clinica.new.seal
  end

  def rendered = Pinecall.render(@agent)

  def test_the_layout_is_the_framework_s_four_blocks_in_send_order
    assert_equal %w[identity knowledge tools view], rendered.blocks.map(&:name)
    assert_equal %w[static static static dynamic], rendered.blocks.map(&:region)
    assert_equal Pinecall::Prompt::FRAMEWORK, Clinica.wire_config[:prompt]
  end

  def test_the_static_blocks_joined_are_one_text_the_docstring_the_words_the_tools
    whole = [
      @agent.doc,
      "<rules>\n#{Pinecall::Rules::RULES}\n</rules>",
      "<protocols>\n#{Pinecall::Rules::PROTOCOLS}\n</protocols>",
      "<channel>\n#{Pinecall::Rules::SPOKEN}\n</channel>",
      "<tools>\n- find_patient: Busca al paciente.\n</tools>"
    ].join("\n\n")

    assert_equal whole, rendered.instructions
  end

  def test_the_identity_block_is_the_docstring_and_the_framework_s_words
    text = rendered[:identity]

    assert_includes text, "Eres la recepción de Clínica Norte."
    assert_includes text, "<rules>"
    assert_includes text, "<protocols>"
    refute_includes text, "find_patient"
  end

  # The gateway fills `knowledge` from the agent's settings.
  def test_the_knowledge_block_is_the_gateway_s_and_the_class_sends_nothing_for_it
    assert_equal "", rendered[:knowledge]
  end

  def test_the_tools_block_is_every_tool_the_class_declares
    assert_includes rendered[:tools], "- find_patient: Busca al paciente."
  end

  def test_the_static_blocks_do_not_move_when_the_state_does
    before = rendered.static.map(&:text)
    @agent.run_tool(:find_patient, name: "Marta")

    assert_equal before, rendered.static.map(&:text)
  end

  def test_the_view_block_is_the_view_and_it_moves
    assert_includes rendered[:view], "Saluda y pide nombre y teléfono."

    @agent.run_tool(:find_patient, name: "Marta")

    assert_includes rendered[:view], "Hablas con Marta."
    refute_includes rendered[:view], "Saluda"
  end

  # Lookup results reach the model as tool results, never inside a prompt block.
  def test_no_block_of_the_prompt_carries_anything_a_lookup_returned
    Pinecall::Agent::Author.with("the test") { @agent.slots = ["martes 10:00"] }
    page = Pinecall.render(@agent, remembered: ["le gusta por la mañana"])

    assert_empty page.blocks.map(&:text).select { |text| text.include?("<!--") }
    refute_includes page.instructions, "le gusta por la mañana"
    refute_includes page[:view], "le gusta por la mañana"
  end

  def test_what_the_agent_remembers_reaches_the_view_as_a_question_it_may_ask
    assert_includes Pinecall.render(@agent, remembered: ["le gusta por la mañana"])[:view],
                    "Ofrécele primero las horas de la mañana."
    refute_includes rendered[:view], "Ofrécele primero"
  end

  def test_the_view_reads_what_surrounds_the_call_and_not_only_the_state
    assert_includes Pinecall.render(@agent, resumed: true)[:view], "Se cortó su llamada anterior."
  end

  def test_a_template_is_read_by_a_person_and_the_ragged_edges_come_off_for_the_model
    Pinecall::Agent::Author.with("the test") { @agent.slots = ["martes 10:00", "martes 11:00"] }

    assert_includes rendered[:view], "## Horas libres\n\nmartes 10:00\nmartes 11:00"
    refute_match(/\n{3,}/, rendered[:view])
    assert_equal rendered[:view].strip, rendered[:view]
  end

  def test_the_history_carries_the_summaries_a_collapse_left
    @agent.run_tool(:find_patient, name: "Marta")
    @agent.collapse("La paciente ya está identificada.")

    assert_includes rendered.history, "La paciente ya está identificada."
    assert_includes rendered.history, "<!-- collapsed:"
  end

  def test_the_page_a_person_reads_names_every_block_and_the_history_between_the_regions
    page = Pinecall.show_prompt(@agent)

    assert_equal ["── identity (static) ──", "── knowledge (static) ──", "── tools (static) ──",
                  "── history ──", "── view (dynamic) ──"],
                 page.lines.map(&:chomp).select { |line| line.start_with?("── ") }
  end

  def test_a_class_with_no_view_beside_it_has_an_empty_dynamic_block
    silent = Class.new(Pinecall::Agent) { doc "Una tienda sin vista." }

    assert_equal "", Pinecall.render(silent.new.seal)[:view]
  end
end
