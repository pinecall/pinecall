# frozen_string_literal: true

require "test_helper"

# What a mounted agent sends, and when, against the testing gateway.
class BridgeTest < Minitest::Test
  # Eres la recepción de Clínica Norte.
  class Clinica < Pinecall::Agent
    web true

    stage :identify, :book
    state :patient
    state :slots, []
    accepts "agenda.changed", from: %i[app]

    view template: <<~ERB
      <% if stage == :identify -%>
      Pide nombre y teléfono.
      <% end -%>
      <% if patient -%>
      Hablas con <%= patient %>.
      <% end -%>
      <% if slots.any? -%>
      Han cambiado las horas.
      <% end -%>
    ERB

    def on_call(call)
      self.patient = "Marta Ruiz" if call.from == "+34600123456"
      self.stage = :book if patient
    end

    def on_event(name, data, _meta)
      self.slots = data[:slots] if name == "agenda.changed"
    end

    def on_end(_call) = log("goodbye", { patient: })

    # Busca al paciente por su nombre.
    tool stage: :identify
    def find_patient(name:)
      self.patient = name
      self.stage = :book
      { name: }
    end

    # Cuelga.
    tool
    def stop = call.hangup("done")
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    @mounted = Pinecall.mount(Clinica, client: @gateway)
  end

  def test_the_declaration_is_what_the_class_says_about_itself
    assert_equal "clinica", @mounted.slug
    refute @mounted.options.key?(:routes)
    refute @mounted.options.key?(:language)
    assert_equal %w[find_patient stop], @mounted.options[:tools].map { |spec| spec[:name] }
    assert_equal [{ name: "agenda.changed", from: %w[app] }], @mounted.options[:events]
    assert_equal %w[identity knowledge tools view], @mounted.options[:prompt].map { |spec| spec[:name] }
  end

  def test_a_call_opens_with_one_whole_prompt_and_not_one_send_per_field
    call = @gateway.call_started(from: "+34600123456")
    opening = call.commands.map(&:type)

    assert_equal 1, opening.count("state.set")
    assert_includes call.block("identity"), "Eres la recepción de Clínica Norte."
    assert_includes call.prompt, "Hablas con Marta Ruiz."
  end

  def test_the_hook_writes_before_the_first_render_so_the_model_never_reads_a_state_it_was_not_in
    call = @gateway.call_started(from: "+34600123456")

    refute_includes call.prompt, "Pide nombre y teléfono."
    assert_equal "book", call.state[:stage].to_s
  end

  def test_a_tool_the_model_calls_runs_here_and_answers_with_one_result
    call = @gateway.call_started(from: "+34999000111")
    result = call.tool("find_patient", name: "Ana Sanz")

    assert_equal({ name: "Ana Sanz" }, result[:output])
    assert_includes call.prompt, "Hablas con Ana Sanz."
  end

  def test_a_tool_that_refuses_answers_the_model_instead_of_leaving_the_turn_waiting
    call = @gateway.call_started(from: "+34999000111")
    result = call.tool("find_patient")

    assert_includes result[:error], "name"
    assert_nil result[:output]
  end

  def test_a_tool_this_agent_does_not_declare_is_told_so_by_name
    call = @gateway.call_started
    result = call.tool("sing", song: "la traviata")

    assert_includes result[:error], "sing"
  end

  def test_a_static_block_is_sent_once_and_never_again
    call = @gateway.call_started(from: "+34999000111")
    call.tool("find_patient", name: "Ana Sanz")
    sent = call.commands.select { |one| one.type == "prompt.set" }.map { |one| one.data[:name] }

    assert_equal 1, sent.count("identity")
    assert_equal 1, sent.count("tools")
    assert_operator sent.count("view"), :>, 1
  end

  def test_a_block_with_nothing_to_say_costs_no_command_until_it_has_something
    call = @gateway.call_started(from: "+34999000111")

    assert_nil call.block("knowledge")
  end

  def test_a_tool_that_moves_nothing_sends_no_prompt_at_all
    call = @gateway.call_started(from: "+34600123456")
    before = call.commands.count { |sent| sent.type == "prompt.set" }
    call.tool("find_patient", name: "Marta Ruiz")

    assert_equal before, call.commands.count { |sent| sent.type == "prompt.set" }
  end

  def test_the_visible_tools_follow_the_state
    call = @gateway.call_started(from: "+34999000111")

    assert_equal %w[find_patient stop], call.tools

    call.tool("find_patient", name: "Ana Sanz")

    assert_equal %w[stop], call.tools
  end

  def test_a_declared_fact_reaches_the_hook_and_moves_the_prompt
    call = @gateway.call_started(from: "+34600123456")
    call.fact("agenda.changed", { slots: ["martes 10:00"] })

    assert_includes call.prompt, "Han cambiado las horas."
  end

  def test_a_fact_from_somebody_the_class_did_not_declare_never_reaches_the_hook
    call = @gateway.call_started(from: "+34600123456")
    _out, said = capture_subprocess_io do
      call.fact("agenda.changed", { slots: ["martes 10:00"] }, from: "participant")
    end

    refute_includes call.prompt.to_s, "Han cambiado las horas."
    assert_includes said, "agenda.changed from participant" if said && !said.empty?
  end

  def test_a_state_change_caused_by_a_fact_says_so_in_the_log_beside_it
    call = @gateway.call_started(from: "+34600123456")
    call.fact("agenda.changed", { slots: ["martes 10:00"] })
    cause = call.commands.find { |sent| sent.type == "call.log" && sent.data[:name] == "state.cause" }

    assert_equal "slots", cause.data[:data][:field]
    assert_equal "agenda.changed", cause.data[:data][:event]
  end

  def test_a_verb_the_class_calls_on_its_call_is_one_command
    call = @gateway.call_started
    call.tool("stop")

    assert_equal "done", call.last("call.hangup")[:reason]
  end

  def test_the_end_hook_runs_and_the_instance_is_let_go
    call = @gateway.call_started(from: "+34600123456")
    call.ended

    assert_equal "goodbye", call.last("call.log")[:name]
    assert_nil @mounted.serving(call.id)
  end

  def test_two_calls_at_once_never_share_a_state
    first = @gateway.call_started(id: "CA_first", from: "+34999000111")
    second = @gateway.call_started(id: "CA_second", from: "+34600123456")
    first.tool("find_patient", name: "Ana Sanz")

    assert_equal "Ana Sanz", @mounted.serving("CA_first").patient
    assert_equal "Marta Ruiz", @mounted.serving("CA_second").patient
  end

  # A golden, a persona or `?state=` asked for this state: it is the call's from the first render.
  def test_a_call_opens_in_the_state_its_call_started_carries_after_the_hook_and_before_the_first_render
    call = @gateway.call_started(from: "+34600123456", state: { patient: "Ana Pérez" })

    assert_equal 1, call.commands.count { |sent| sent.type == "state.set" }
    assert_equal "Ana Pérez", call.state[:patient]
    assert_includes call.prompt, "Hablas con Ana Pérez."
  end

  def test_a_call_nobody_seeded_opens_in_the_state_its_hook_wrote
    call = @gateway.call_started(from: "+34600123456")

    assert_equal "Marta Ruiz", call.state[:patient]
  end

  # Another process drained or died: this one takes the call where it was, with no on_call.
  def test_a_call_handed_over_mid_conversation_is_served_in_the_state_the_gateway_kept
    call = @gateway.call_attached(state: { stage: "book", patient: "Ana Pérez", slots: [] }, from: "+34600999999")

    assert_includes call.prompt, "Hablas con Ana Pérez."
    refute_includes call.tools, "find_patient"
    assert_equal "Ana Pérez", @mounted.serving(call.id).snapshot[:patient]
  end

  def test_a_call_handed_back_to_the_process_serving_it_sends_its_whole_prompt_again
    call = @gateway.call_started(from: "+34600123456")
    before = call.commands.count { |sent| sent.type == "prompt.set" }

    @gateway.call_attached(id: call.id, state: call.state, from: "+34600123456")

    assert_operator call.commands.count { |sent| sent.type == "prompt.set" }, :>, before
  end

  # Busca en la base de conocimiento.
  class Buscadora < Pinecall::Agent
    web true
    state :said, ""
    view template: <<~ERB
      <% if remembers?("alergia") -%>
      Recuerda su alergia.
      <% end -%>
      <% if call[:claimed] -%>
      Ve la página <%= call[:claimed] %>.
      <% end -%>
    ERB

    # Busca el horario.
    tool
    def horario(q:) = knowledge.search(q, k: 2).map(&:text)
  end

  def test_a_search_goes_through_the_gateway_for_this_call
    gateway = Pinecall::Testing::Gateway.new.finds({ path: "horario.md", heading: "Horario", text: "de 9 a 18" })
    Pinecall.mount(Buscadora, client: gateway)
    call = gateway.call_started

    answer = call.tool("horario", q: "cuándo abren")

    assert_equal ["de 9 a 18"], answer[:output]
    assert_equal [{ call: call.id, query: "cuándo abren", k: 2 }], gateway.searched
  end

  def test_a_class_that_searches_says_so_when_it_registers
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Buscadora, client: gateway).agent.open

    configured = gateway.commands.find { |sent| sent.type == "agent.configure" }
    assert_equal true, configured.data[:config][:uses_knowledge]
  end

  def test_what_memory_recalled_reaches_the_view
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Buscadora, client: gateway)
    call = gateway.call_started
    recalled = { op: "recall", facts: [{ text: "alergia a la penicilina", category: "salud" }], took_ms: 3.0 }

    gateway.deliver("memory.ops", { ops: [recalled] }, call: call.id)
    gateway.settle

    assert_includes call.prompt, "Recuerda su alergia."
  end

  def test_a_claim_reaches_the_view_once_the_log_says_it_took
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Buscadora, client: gateway)
    call = gateway.call_started

    gateway.deliver("call.claimed", { code: "4821", via: "agent" }, call: call.id)
    gateway.settle

    assert_includes call.prompt, "Ve la página 4821."
  end
end
