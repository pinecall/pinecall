# frozen_string_literal: true

require "test_helper"

# The gem's reducer and reader hold to the runtime's golden call log and the state it folds to.
class ReduceTest < Minitest::Test
  # Copied from the runtime's tests/wire/golden/: when its wire moves, these two files move with it.
  GOLDEN = File.expand_path("golden", __dir__)

  def entries
    JSON.parse(File.read(File.join(GOLDEN, "call-log.json")), symbolize_names: true)
        .map { |raw| Pinecall::Wire.decode_entry(raw) }
  end

  def test_every_entry_of_the_golden_log_reads_as_the_event_its_type_names
    entries.each { |entry| assert_equal entry.type, Pinecall::Wire.event_of(entry).type }
  end

  def test_the_golden_log_folds_to_the_state_the_runtime_folds_it_to
    expected = JSON.parse(File.read(File.join(GOLDEN, "call-log.state.json")))
    folded = JSON.parse(JSON.generate(Pinecall::Wire.reduce(entries)))
    assert_equal expected, folded
  end
end
