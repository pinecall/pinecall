# frozen_string_literal: true

require "test_helper"

# What leaves the gem as a command: a Ruby value as the JSON the wire carries.
class CodecTest < Minitest::Test
  Visita = Struct.new(:dia)
  Ficha = Data.define(:nombre, :visitas)

  def command(data) = Pinecall::Wire.command(type: "state.set", agent: "clinica", call: "CA_1", data:)

  def test_a_data_or_a_struct_in_a_command_is_its_fields_wherever_it_sits
    sent = command({ state: { ficha: Ficha.new(nombre: "Ana", visitas: [Visita.new("lunes")]) } })

    assert_equal({ ficha: { nombre: "Ana", visitas: [{ dia: "lunes" }] } }, sent.data[:state])
    assert_includes Pinecall::Wire.encode(sent), '"ficha":{"nombre":"Ana","visitas":[{"dia":"lunes"}]}'
  end

  def test_everything_else_goes_as_it_is
    sent = command({ state: { stage: :book, slots: ["10:00"], note: nil, when: 1.5 } })

    assert_equal({ stage: :book, slots: ["10:00"], note: nil, when: 1.5 }, sent.data[:state])
  end
end
