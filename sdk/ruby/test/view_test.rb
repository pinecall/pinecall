# frozen_string_literal: true

require "test_helper"

class ViewTest < Minitest::Test
  def rendered(template, state = {}, remembered = [])
    Pinecall::View.inline(template).render(Pinecall::Reading.new(state, remembered))
  end

  def test_every_state_field_is_in_scope_by_its_own_name
    assert_equal "Hablas con Marta Ruiz.",
                 rendered("Hablas con <%= patient %>.", { patient: "Marta Ruiz" })
  end

  def test_a_field_the_class_never_declared_is_refused_rather_than_read_as_nothing
    assert_raises(NameError) { rendered("<%= paciente %>") }
  end

  def test_what_the_agent_remembers_about_this_caller_decides_a_sentence_and_is_never_printed
    text = rendered(%(<% if remembers?("médico habitual") -%>\nOfrece sus horas.\n<% end -%>),
                    {}, ["su médico habitual es la doctora Vidal"])

    assert_equal "Ofrece sus horas.", text
    refute_includes text, "doctora Vidal"
  end

  def test_a_view_nobody_told_what_is_remembered_answers_no_rather_than_guessing
    assert_equal "", rendered(%(<% if remembers?("alergias") -%>\nPregúntale.\n<% end -%>))
  end

  def test_a_template_is_read_by_a_person_and_the_ragged_edges_come_off_for_the_model
    text = rendered("\n\n Hola.   \n\n\n\n  Adiós.  \n\n")

    assert_equal "Hola.\n\n  Adiós.", text
  end

  def test_a_template_can_take_the_whole_state_and_lay_a_list_out_one_per_line
    assert_equal "el martes\nel jueves",
                 rendered("<%= each_line(state[:slots]) %>", { slots: ["el martes ", " el jueves"] })
  end
end
