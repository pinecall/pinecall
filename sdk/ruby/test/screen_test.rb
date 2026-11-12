# frozen_string_literal: true

require "test_helper"

# A screen: parts a page draws its own way, scenes the model moves, and what it reads of them.
class ScreenTest < Minitest::Test
  Agenda = Pinecall.part("agenda")
  Slot = Pinecall.part("slot")

  # Desk.
  class Desk < Pinecall::Agent
    scenes agenda: "the open times you read"

    def screen = Agenda.(day: "lunes")
  end

  def test_a_part_is_named_in_lowercase_since_the_page_maps_the_name
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.part("Agenda") }
  end

  def test_a_screen_is_its_parts_and_words_in_order
    drawn = [Agenda.(Slot.(at: "9:00"), "o más tarde", day: "lunes"), nil, ""]

    assert_equal [{ part: "agenda", props: { day: "lunes" },
                    children: [{ part: "slot", props: { at: "9:00" }, children: [] }, "o más tarde"] }],
                 Pinecall::Screen.screen_of(drawn)
    assert_raises(Pinecall::DeclarationRefused) { Pinecall::Screen.screen_of([Object.new]) }
  end

  def test_a_class_draws_a_screen_when_it_writes_its_own
    assert Pinecall::Screen.draws?(Desk)
    refute Pinecall::Screen.draws?(Class.new(Pinecall::Agent))
  end

  def test_scenes_are_named_in_lowercase_each_with_words_and_none_is_taken
    assert_equal({ "agenda" => "the open times you read" }, Desk.declared_scenes)
    assert_raises(Pinecall::DeclarationRefused) { Class.new(Pinecall::Agent) { scenes none: "nothing" } }
  end

  def test_the_screen_tool_offers_every_scene_and_none_and_the_model_reads_which_is_up
    spec = Pinecall::Screen.showing_tool({ "agenda" => "the open times" })

    assert_equal %w[agenda none], spec[:parameters][:properties][:scene][:enum]
    assert spec[:quiet]
    assert_equal "", Pinecall::Screen.scene_line({}, nil)
    assert_includes Pinecall::Screen.scene_line({ "agenda" => "times" }, "agenda"), "shows agenda (times)"
  end
end
