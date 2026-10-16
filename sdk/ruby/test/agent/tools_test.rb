# frozen_string_literal: true

require "test_helper"

class ToolsTest < Minitest::Test
  # Una clínica que da horas.
  class Clinica < Pinecall::Agent
    stage :identify, :book
    state :slots, []

    # Busca al paciente por nombre y teléfono.
    # Pide los dos antes de llamarla.
    tool stage: :identify, pii: %i[name phone]
    def find_patient(name:, phone:)
      { name:, phone: }
    end

    # Horas libres de un día.
    tool stage: :book, preview: 2, announce: "Voy a mirar la agenda.", params: { day: String, how_many: Integer }
    def free_slots(day:, how_many: 3)
      Array.new(how_many) { |at| "#{day} #{10 + at}:00" }
    end

    # Reserva la hora que el paciente ya ha confirmado.
    tool stage: :book, confirm: "Le reservo el {{chosen}}. ¿Lo confirmo?", timeout: 8
    def book(chosen:)
      chosen
    end
  end

  def setup
    @agent = Clinica.new.seal
  end

  def spec_of(name) = @agent.tools.find { |spec| spec[:name] == name.to_s }

  def test_the_comment_above_the_declaration_is_what_the_model_reads_on_one_line
    assert_equal "Busca al paciente por nombre y teléfono. Pide los dos antes de llamarla.",
                 spec_of(:find_patient)[:description]
  end

  def test_a_comment_ends_at_its_first_tag_and_drops_its_blank_lines
    assert_equal "Una frase. Otra, tras una línea vacía.",
                 Pinecall::Agent::Doc.one_line(["Una frase.", "", "Otra, tras una línea vacía.", "@param x nada"])
  end

  def test_the_parameters_are_the_method_s_own_keywords
    parameters = spec_of(:free_slots)[:parameters]

    assert_equal %i[day how_many], parameters[:properties].keys
    assert_equal ["day"], parameters[:required]
    assert_equal({ type: "integer" }, parameters[:properties][:how_many])
    assert_equal false, parameters[:additionalProperties]
  end

  def test_a_parameter_nobody_typed_is_text_because_that_is_what_a_caller_says
    assert_equal({ type: "string" }, spec_of(:find_patient)[:parameters][:properties][:name])
  end

  def test_an_announcement_travels_as_the_wire_carries_it
    assert_equal "Voy a mirar la agenda.", spec_of(:free_slots)[:announce]
    assert_nil spec_of(:book)[:announce]
  end

  def test_a_read_back_is_what_makes_a_tool_irreversible_on_the_wire
    assert_equal "irreversible", spec_of(:book)[:side_effect]
    assert_equal "read", spec_of(:find_patient)[:side_effect]
    assert_in_delta 8.0, spec_of(:book)[:timeout_s]
  end

  def test_a_declared_pii_parameter_travels_as_the_wire_carries_it
    assert_equal %w[name phone], spec_of(:find_patient)[:pii]
  end

  def test_only_the_tools_this_state_shows_are_visible
    assert_equal %w[find_patient], @agent.visible_tools.map { |spec| spec[:name] }

    Pinecall::Agent::Author.with("the test") { @agent.stage = :book }

    assert_equal %w[free_slots book], @agent.visible_tools.map { |spec| spec[:name] }
  end

  def test_a_preview_cuts_what_the_model_sees_and_not_what_the_state_keeps
    Pinecall::Agent::Author.with("the test") { @agent.stage = :book }

    assert_equal ["martes 10:00", "martes 11:00"], @agent.run_tool(:free_slots, day: "martes")
  end

  def test_a_tool_with_no_docstring_is_refused_because_no_model_could_choose_it
    refused = assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) do
        tool
        def silent = nil
      end
    end

    assert_includes refused.message, "docstring"
  end

  def test_a_tool_that_takes_a_positional_argument_is_refused_with_the_reason
    refused = assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) do
        tool doc: "Reserva."
        def book(chosen) = chosen
      end
    end

    assert_includes refused.message, "keyword arguments"
  end

  def test_pii_naming_a_parameter_the_tool_does_not_have_is_refused
    refused = assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) do
        tool doc: "Busca.", pii: %i[dni]
        def find(name:) = name
      end
    end

    assert_includes refused.message, "dni"
  end

  def test_a_stage_the_class_does_not_declare_is_refused_at_load
    refused = assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) do
        stage :identify, :book
        tool doc: "Paga.", stage: :pay
        def pay = nil
      end
    end

    assert_includes refused.message, "pay"
  end

  def test_a_staged_tool_on_a_class_with_no_stage_field_says_what_to_add
    refused = assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) do
        tool doc: "Paga.", stage: :pay
        def pay = nil
      end
    end

    assert_includes refused.message, "declares none"
  end

  def test_an_argument_the_tool_never_asked_for_is_refused_before_the_method_runs
    refused = assert_raises(Pinecall::ToolFailed) { @agent.run_tool(:find_patient, name: "a", dni: "b") }

    assert_includes refused.message, "dni"
  end

  def test_a_subclass_keeps_its_parent_s_tools
    quieter = Class.new(Clinica) do
      # Cuelga.
      tool
      def hang_up = :done
    end

    assert_equal %w[find_patient free_slots book hang_up], quieter.new.tools.map { |spec| spec[:name] }
  end
end
