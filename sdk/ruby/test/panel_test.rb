# frozen_string_literal: true

require "test_helper"

# Drawing a panel to the console's nodes: the same JSON the TypeScript package's tags give.
class PanelTest < Minitest::Test
  # La ficha del cliente, para la consola.
  class Mudanzas < Pinecall::Agent
    def self.since(contact) = contact == "+34600" ? "12 Mar 2024" : nil

    panel "Ficha del cliente" do |who|
      panel "Cliente" do
        rows do
          row "Alta", since(who.contact)
          row "Zona", "Centro"
        end
      end
    end
  end

  WHO = Pinecall::Panel::Who.new(agent: "mudanzas", contact: "+34600", call: "CA_1")

  def drawn(&) = Pinecall::Panel::Drawing.new(Mudanzas).tap { |drawing| drawing.instance_exec(&) }.nodes

  def test_a_panel_is_one_node_with_its_children_under_it_and_the_classs_helpers_at_hand
    assert_equal({ name: "Ficha del cliente",
                   nodes: [{ tag: "panel", title: "Cliente", children: [
                     { tag: "rows", children: [{ tag: "row", label: "Alta", value: "12 Mar 2024" },
                                               { tag: "row", label: "Zona", value: "Centro" }] }
                   ] }] },
                 Pinecall::Panel.draw(Mudanzas, WHO))
  end

  def test_a_number_is_written_out_wherever_it_is
    assert_equal [{ tag: "stat", label: "Servicios", value: "3" }], drawn { stat "Servicios", 3 }
    assert_equal [{ tag: "stat", label: "Media", value: "2.5" }], drawn { stat "Media", 2.5 }
  end

  def test_a_tables_rows_are_read_by_the_columns_own_names_or_in_their_order
    assert_equal [{ tag: "table", columns: %w[fecha servicio importe], rows: [["12 Mar", "Mudanza", "240"]] }],
                 drawn { table columns: %w[fecha servicio importe], rows: [{ fecha: "12 Mar", "servicio" => "Mudanza", importe: 240 }] }
    assert_equal [{ tag: "table", columns: %w[a b], rows: [%w[uno dos]] }], drawn { table columns: %w[a b], rows: [%w[uno dos]] }
  end

  def test_a_badge_keeps_its_tone_and_one_it_does_not_know_is_neutral
    assert_equal [{ tag: "badge", tone: "warn", text: "con saldo" }], drawn { badge "con saldo", tone: :warn }
    assert_equal [{ tag: "badge", tone: "neutral", text: "al día" }], drawn { badge "al día", tone: :turquoise }
  end

  def test_what_the_view_left_out_draws_nothing
    assert_equal [{ tag: "panel", title: nil, children: [] }], drawn { panel { text "" } }
  end

  def test_the_declaration_names_the_panel_and_only_the_name
    assert_equal({ name: "Ficha del cliente" }, Mudanzas.wire_config(tools: [])[:view])
  end

  def test_a_class_draws_one_panel_and_a_subclass_inherits_none
    error = assert_raises(Pinecall::DeclarationRefused) { Mudanzas.panel("Otra") { nil } }

    assert_equal "PanelTest::Mudanzas declares two panels (Ficha del cliente and Otra); a class draws one panel", error.message
    assert_nil Class.new(Mudanzas).declared_panel
  end
end
