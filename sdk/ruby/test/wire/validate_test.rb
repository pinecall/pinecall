# frozen_string_literal: true

require "test_helper"

# A value checked against a named shape: what the runtime writes reads, what it never writes does not.
class ValidateTest < Minitest::Test
  def test_an_optional_field_the_runtime_wrote_as_null_reads_as_absent
    turn = { text: "hola", speech_id: "sp_1", item_id: "it_1", metrics: {}, language: nil }
    assert_equal turn, Pinecall::Wire::Validate.call!("UserTurnEnded", turn, where: "turn.user")
  end

  def test_a_tool_that_answered_nothing_is_a_result_with_no_output
    result = { call_id: "tc_1", name: "find_patient", output: nil }
    assert_equal result, Pinecall::Wire::Validate.call!("ToolResult", result, where: "tool.result")
  end

  def test_a_call_started_reads_with_the_state_it_opens_in_and_without_one
    started = { channel: "web", direction: "inbound", from: "web_7fb3", to: "clinica", caller: nil, started_at: 1.5 }
    assert_equal started, Pinecall::Wire::Validate.call!("CallStarted", started, where: "call.started")
    opened = started.merge(state: { patient_name: "Ana" })
    assert_equal opened, Pinecall::Wire::Validate.call!("CallStarted", opened, where: "call.started")
  end

  def test_a_spoken_call_started_names_the_worker_that_runs_it
    started = { channel: "phone", direction: "inbound", from: "+34600", to: "+34910", caller: nil,
                started_at: 1.5, env: "production", worker: "pinecall-runtime-a" }
    assert_equal started, Pinecall::Wire::Validate.call!("CallStarted", started, where: "call.started")
  end

  def test_a_register_may_say_it_answers_the_console
    register = { routes: [], takes_unclaimed: false, answers_dev: true }
    assert_equal register, Pinecall::Wire::Validate.call!("AgentRegister", register, where: "agent.register")
  end

  def test_a_score_says_which_judge_gave_it
    score = { passed: true, judges: [], judge_calls: 2, judge_cost_usd: 0.003,
              judged_by: { provider: "anthropic", model: "claude-haiku-5-5", criteria: "c0ffee" } }
    assert_equal score, Pinecall::Wire::Validate.call!("CallScore", score, where: "call.score")
  end

  def test_a_score_reads_na_a_classification_its_evals_and_whose_key_judged
    evidence = { seqs: [4] }
    score = { judges: [
                { name: "identified", verdict: "na", criteria: "q", reason: "it came in", evidence: },
                { name: "sentiment", verdict: "classified", criteria: "q", reason: "calm", evidence:, score: 4 },
                { name: "intent", verdict: "classified", criteria: "q", reason: "booking", evidence:, choice: "book" }
              ],
              judge_calls: 3, evals: 2, own_key: true }
    assert_equal score, Pinecall::Wire::Validate.call!("CallScore", score, where: "call.score")
  end

  def test_a_summary_says_a_simulated_caller_played_the_call
    summary = { reason: "caller_hung_up", outcome: "booked", duration_s: 40.0, turns: 6, usage: [],
                cost: { usd: 0.01, rows: [], unpriced: [] }, simulated: true }
    assert_equal summary, Pinecall::Wire::Validate.call!("CallSummary", summary, where: "call.summary")
  end

  def test_a_written_goldens_summary_names_its_run_and_a_judge_tried_reads
    summary = { reason: "caller_hung_up", outcome: "booked", duration_s: 40.0, turns: 6, usage: [],
                cost: { usd: 0.01, rows: [], unpriced: [] }, run: "run_8f4a2c" }
    assert_equal summary, Pinecall::Wire::Validate.call!("CallSummary", summary, where: "call.summary")
    tried = { kind: "try", name: "grounded", env: "sandbox", calls: %w[call_1 call_2], evals: 2, judge_calls: 2 }
    assert_equal tried, Pinecall::Wire::Validate.call!("EvalsSpent", tried, where: "evals.spent")
    refused = { org: "org_1", quota: "evals", used: 500.0, limit: 500 }
    assert_equal refused, Pinecall::Wire::Validate.call!("CreditsExhausted", refused, where: "credits.exhausted")
  end

  def test_a_required_field_still_has_to_be_there
    error = assert_raises(Pinecall::Wire::WireError) do
      Pinecall::Wire::Validate.call!("ToolResult", { name: "find_patient" }, where: "tool.result")
    end
    assert_match "requires it", error.message
  end
end
