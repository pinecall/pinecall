# frozen_string_literal: true

require "test_helper"

# What a class holds, returns and logs reaches the wire as JSON, whatever Ruby value it is.
class BridgeValuesTest < Minitest::Test
  Visita = Struct.new(:dia, :hora)
  Ficha = Data.define(:nombre, :visitas)

  # Guarda lo que encuentra.
  class Archivista < Pinecall::Agent
    web true
    state :ficha

    # Devuelve lo que encontró, tal cual.
    tool
    def fragmentos(q:) = knowledge.search(q, k: 2)

    # Devuelve la ficha de una paciente.
    tool
    def ficha_de_marta
      { ficha: Ficha.new(nombre: "Marta", visitas: [Visita.new("lunes", "10:00")]), otras: [Visita.new("martes", "11:00")] }
    end

    # Guarda la ficha y la anota.
    tool
    def guardar
      self.ficha = Ficha.new(nombre: "Ana", visitas: [Visita.new("jueves", "9:00")])
      log("guardada", Visita.new("jueves", "9:00"))
      log("detalle", { ficha: })
    end
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new.finds({ path: "horario.md", heading: "Horario", text: "de 9 a 18" })
    Pinecall.mount(Archivista, client: @gateway)
    @call = @gateway.call_started
  end

  def test_a_tool_that_returns_what_it_searched_hands_the_model_the_fields_and_not_their_inspect
    answer = @call.tool("fragmentos", q: "cuándo abren")

    found = { path: "horario.md", heading: "Horario", text: "de 9 a 18" }
    assert_equal [found], answer[:output]
    assert_equal [found], JSON.parse(JSON.generate(answer[:output]), symbolize_names: true)
  end

  def test_a_struct_or_a_data_is_its_fields_wherever_it_sits_in_what_a_tool_returns
    answer = @call.tool("ficha_de_marta")

    assert_equal({ nombre: "Marta", visitas: [{ dia: "lunes", hora: "10:00" }] }, answer[:output][:ficha])
    assert_equal [{ dia: "martes", hora: "11:00" }], answer[:output][:otras]
  end

  def test_a_data_held_in_a_state_field_goes_up_as_its_fields
    @call.tool("guardar")

    assert_equal({ nombre: "Ana", visitas: [{ dia: "jueves", hora: "9:00" }] }, @call.state[:ficha])
  end

  def test_a_struct_or_a_data_in_a_logged_line_goes_up_as_its_fields
    @call.tool("guardar")

    assert_equal({ dia: "jueves", hora: "9:00" }, @call.last("call.log", name: "guardada")[:data])
    assert_equal({ ficha: { nombre: "Ana", visitas: [{ dia: "jueves", hora: "9:00" }] } },
                 @call.last("call.log", name: "detalle")[:data])
  end
end
