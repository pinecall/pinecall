# frozen_string_literal: true

require "test_helper"

# A voice app: its lines, its rules, what its agents share, the page, and what it hears.
class VoiceAppTest < Minitest::Test
  # You answer the clinic's phone.
  class FrontDesk < Pinecall::Agent; end

  # You answer questions about bills.
  class Billing < Pinecall::Agent
    takes "questions about a bill"
  end

  # It greets on its own.
  class Greets < Pinecall::Agent
    greeting "Hola."
  end

  def test_an_app_is_named_like_its_folder_and_keeps_its_clock_in_a_zone
    assert_equal "America/Los_Angeles", Pinecall.voice_app("brightside", timezone: "America/Los_Angeles").timezone
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.voice_app("Brightside") }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.voice_app("brightside", timezone: "nowhere") }
  end

  def test_a_line_is_a_number_with_its_country_code_answered_once_by_an_agent
    app = Pinecall.voice_app("brightside").line("+1 (415) 555-0134", FrontDesk, greeting: "Brightside.")

    assert_equal "+14155550134", app.lines.first.number
    assert_raises(Pinecall::DeclarationRefused) { app.line("555 0134", FrontDesk) }
    assert_raises(Pinecall::DeclarationRefused) { app.line("+14155550134", Billing) }
    assert_raises(Pinecall::DeclarationRefused) { app.line("+14155550135", FrontDesk) }
  end

  def test_a_teammate_says_what_it_takes_and_a_line_that_chooses_names_its_fallback
    app = Pinecall.voice_app("brightside")

    assert_raises(Pinecall::DeclarationRefused) { app.line("+14155550134", FrontDesk, team: [Greets]) }
    assert_raises(Pinecall::DeclarationRefused) { app.line("+14155550134", ->(_) { Billing }, team: [Billing]) }
    app.line("+14155550134", ->(_) { Billing }, team: [Billing], fallback: FrontDesk)

    assert_equal [FrontDesk, Billing], app.team_of(Billing)
    refute_nil app.choosing(FrontDesk)
  end

  def test_what_the_app_declares_for_its_agents_and_a_setting_both_declare_is_refused
    app = Pinecall.voice_app("brightside", timezone: "America/Los_Angeles")
                  .line("+14155550134", FrontDesk, greeting: "Brightside.")
                  .rule("Never quote a price.")
                  .silence(after: "8s", say: "¿Sigues ahí?", times: 2)
    declared = app.declares(FrontDesk)

    assert_equal({ say: "Brightside." }, declared[:greeting])
    assert_equal "America/Los_Angeles", declared[:timezone]
    assert_equal({ says: ["¿Sigues ahí?"], after_s: 8.0, times: 2 }, declared[:idle])
    assert_equal ["app-rule-1"], declared[:judges][:own].map { |judge| judge[:name] }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.voice_app("other").line("+14155550199", Greets, greeting: "Otra.").declares(Greets) }
  end

  def test_a_page_is_a_folder_inside_the_project_reaching_the_first_lines_agent
    app = Pinecall.voice_app("brightside").line("+14155550134", FrontDesk).page("./ui/dist/")

    assert_equal ["ui/dist", FrontDesk], [app.paged.dir, app.paged.answers]
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.voice_app("other").line("+14155550134", FrontDesk).page("../x") }
    assert_raises(Pinecall::DeclarationRefused) { Pinecall.voice_app("other").page("ui/dist") }
  end

  def test_an_entry_reaches_its_handlers_by_name_a_logged_line_by_its_own
    heard = []
    failed = []
    app = Pinecall.voice_app("brightside")
    app.on("visit.booked") { |_call, _data| raise "down" }
    app.on("visit.booked") { |call, data| heard << [call.id, data] }
    app.heard("custom", "CA_1", "front-desk", { name: "visit.booked", data: { id: 7 } }, ->(name, _) { failed << name })

    assert_equal [["CA_1", { id: 7 }]], heard
    assert_equal ["visit.booked"], failed
  end

  def test_a_flow_handed_to_on_is_started_by_the_entry_and_two_of_one_name_are_refused
    remind = Pinecall.flow("remind-visit") { |_visit, step| step.sleep("1h") }
    app = Pinecall.voice_app("brightside").on("visit.booked", remind)

    assert_equal [remind], app.started_by("visit.booked")
    again = Pinecall.flow("remind-visit") { |_visit, step| step.sleep("1h") }
    assert_raises(Pinecall::DeclarationRefused) { app.on("visit.moved", again) }
  end
end
