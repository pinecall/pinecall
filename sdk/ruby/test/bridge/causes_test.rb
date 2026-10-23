# frozen_string_literal: true

require "test_helper"

# Who made each state write, as the entry it is sent in says it: the tool and the model's id for its call,
# the outside fact, or the lifecycle hook.
class BridgeCausesTest < Minitest::Test
  # Eres la recepción de Clínica Norte.
  class Recepcion < Pinecall::Agent
    stage :identify, :book
    state :patient
    state :slots, []
    state :note
    accepts "agenda.changed", from: %i[app]

    def on_call(call)
      self.patient = "Marta Ruiz" if call.from == "+34600123456"
      self.stage = :book if patient
    end

    def on_event(name, data, _meta)
      self.slots = data[:slots] if name == "agenda.changed"
    end

    def on_memory(_ops, _call) = self.note = "recordado"

    # Busca al paciente por su nombre.
    tool stage: :identify
    def find_patient(name:)
      self.patient = name
      self.stage = :book
      { name: }
    end
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Recepcion, client: @gateway)
  end

  def written(call) = call.commands.select { |sent| sent.type == "state.set" }

  def test_what_the_call_hook_wrote_opens_the_call_with_the_hook_as_the_cause
    opening = written(@gateway.call_started(from: "+34600123456")).first

    assert_equal %w[patient stage], opening.data[:changed]
    assert_equal({ kind: "hook", hook: "on_call" }, opening.data[:cause])
  end

  def test_a_call_whose_hook_wrote_nothing_opens_with_the_whole_state_and_no_cause
    opening = written(@gateway.call_started(from: "+34999000111")).first

    refute opening.data.key?(:changed)
    refute opening.data.key?(:cause)
  end

  def test_every_write_of_a_tool_says_which_tool_and_which_call_of_the_model_made_it
    call = @gateway.call_started(from: "+34999000111")
    before = written(call).size
    result = call.tool("find_patient", name: "Ana Sanz")
    cause = { kind: "tool", tool: "find_patient", call_id: result[:call_id] }

    assert_equal [%w[patient], %w[stage]], written(call).drop(before).map { |sent| sent.data[:changed] }
    assert_equal [cause, cause], written(call).drop(before).map { |sent| sent.data[:cause] }
  end

  def test_a_write_a_fact_caused_names_the_fact_in_the_entry_it_is_sent_with
    call = @gateway.call_started(from: "+34600123456")
    fact = @gateway.deliver("event.received", { name: "agenda.changed", data: { slots: ["martes 10:00"] }, source: "app" },
                            call: call.id)
    @gateway.settle

    assert_equal %w[slots], written(call).last.data[:changed]
    assert_equal({ kind: "event", name: "agenda.changed", seq: fact.seq }, written(call).last.data[:cause])
    assert_empty call.commands.select { |sent| sent.type == "call.log" && sent.data[:name] == "state.cause" }
  end

  def test_a_write_in_the_memory_hook_names_that_hook
    call = @gateway.call_started
    recalled = { op: "recall", facts: [{ text: "alergia a la penicilina", category: "salud" }], took_ms: 3.0 }
    @gateway.deliver("memory.ops", { ops: [recalled] }, call: call.id)
    @gateway.settle

    assert_equal({ kind: "hook", hook: "on_memory" }, written(call).last.data[:cause])
  end
end
