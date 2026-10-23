# frozen_string_literal: true

require "test_helper"

# A hook that raises fails its own call, never the process, and the call's log says which hook and why.
class BridgeHooksTest < Minitest::Test
  # Saluda.
  class Torpe < Pinecall::Agent
    state :seen, []
    accepts "slot.released", from: %i[app]
    view template: "Buenas."

    def on_call(call)
      raise "el saludo se rompió" if call.from == "+34000000001"

      self.seen = seen + ["opened"]
    end

    def on_event(name, _data, _meta) = raise "#{name} no se pudo procesar"

    def on_end(_call) = raise "la despedida se rompió"

    # Anota.
    tool
    def anotar = self.seen = seen + ["noted"]
  end

  def setup
    @gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(Torpe, client: @gateway)
  end

  def test_an_on_call_that_raises_leaves_an_entry_and_the_call_opens_all_the_same
    _out, said = capture_io { @call = @gateway.call_started(from: "+34000000001") }

    assert_equal({ hook: "on_call", error: "RuntimeError", message: "el saludo se rompió" }, failed(@call).data[:data])
    assert_includes said, "on_call raised"
    assert_equal "Buenas.", @call.prompt
    assert_equal ["noted"], @call.tool("anotar")[:output]
  end

  def test_an_on_event_that_raises_names_the_event_and_leaves_no_cause_on_the_next_write
    @call = @gateway.call_started(from: "+34600000000")
    capture_io { @call.fact("slot.released", { id: 1 }) }
    @call.tool("anotar")

    assert_equal "slot.released", failed(@call).data[:data][:event]
    write = @call.commands.reverse.find { |sent| sent.type == "state.set" }
    assert_equal "tool", write.data.dig(:cause, :kind)
  end

  def test_an_on_end_that_raises_still_closes_the_log_and_says_done
    @call = @gateway.call_started(from: "+34600000000")
    capture_io { @call.ended }

    assert_equal "on_end", failed(@call).data[:data][:hook]
    assert_equal "call.done", @call.commands.last.type
  end

  private

  def failed(call) = call.commands.find { |sent| sent.type == "call.log" && sent.data[:name] == "hook.failed" }
end
