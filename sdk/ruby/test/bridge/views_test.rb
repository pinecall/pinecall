# frozen_string_literal: true

require "test_helper"

# A view that raises fails its own call, never the process, and the call's log says why.
class BridgeViewsTest < Minitest::Test
  # Saluda.
  class Fragil < Pinecall::Agent
    state :note
    view template: <<~ERB
      <% raise "la vista se rompió" if note == "mala" || call[:from] == "+34000000001" -%>
      Buenas.
    ERB

    # Estropea la nota.
    tool
    def estropear = self.note = "mala"

    # Responde.
    tool
    def responder = "hecho"
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Fragil, client: @gateway)
  end

  def test_a_view_that_fails_at_the_start_leaves_an_entry_naming_the_exception_and_the_call_goes_on
    _out, said = capture_io { @call = @gateway.call_started(from: "+34000000001") }
    failed = @call.commands.find { |sent| sent.type == "call.log" && sent.data[:name] == "render.failed" }

    assert_equal({ error: "RuntimeError", message: "la vista se rompió" }, failed.data[:data])
    assert_includes said, "could not render its view"
    assert_equal "hecho", @call.tool("responder")[:output]
  end

  def test_a_view_that_fails_mid_call_keeps_the_one_the_model_had_and_fails_only_that_call
    @call = @gateway.call_started(from: "+34600000000")
    capture_io { @other = @gateway.call_started(from: "+34000000001", id: "CA_other") }

    _out, _said = capture_io { @call.tool("estropear") }
    failed = @call.commands.select { |sent| sent.type == "call.log" && sent.data[:name] == "render.failed" }

    assert_equal 1, failed.size
    assert_equal "Buenas.", @call.prompt
    assert_nil @other.prompt
    assert_equal "hecho", @call.tool("responder")[:output]
  end

  # Names a field it never declared once a note says so.
  class Despistada < Pinecall::Agent
    state :customer, visibility: :pii
    view template: <<~ERB
      <% if customer -%><%= a_field_the_class_never_declared %><% end -%>
      <% if resumed -%>No saludes otra vez.<% end -%>
    ERB

    # Identifica al cliente.
    tool
    def identificar = self.customer = { name: "Ana Ruiz", phone: "600000001" }
  end

  # R F6: the warning carried Ruby's NameError message, the view's context inspected, the pii state in it.
  def test_a_view_naming_what_nothing_answers_says_the_name_and_never_the_state
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Despistada, client: gateway)
    call = gateway.call_started(from: "+34600000000")
    _out, said = capture_io { call.tool("identificar") }
    failed = call.commands.find { |sent| sent.type == "call.log" && sent.data[:name] == "render.failed" }

    assert_match(/the view names a_field_the_class_never_declared, which is no field/, failed.data[:data][:message])
    assert_includes said, "a_field_the_class_never_declared"
    refute_includes said, "Ana Ruiz"
  end

  # R F6's sibling, P F3 in Python: `resumed` was never true on a live call, a handover included.
  def test_a_call_handed_over_renders_its_view_resumed
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Despistada, client: gateway)
    call = gateway.call_attached(state: {})

    assert_equal "No saludes otra vez.", call.prompt
  end
end
