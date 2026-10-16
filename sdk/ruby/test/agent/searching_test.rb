# frozen_string_literal: true

require "test_helper"

# Whether a class searches its bases, read off its source: a call in code counts, the words do not.
class SearchingTest < Minitest::Test
  Searching = Pinecall::Agent::Searching

  def test_a_tool_that_searches_the_knowledge_counts
    assert Searching.in_source?("def horario(q:)\n  knowledge.search(q, k: 3)\nend")
  end

  def test_the_words_in_a_comment_or_a_string_do_not
    refute Searching.in_source?("# knowledge.search the bases\nsaid = \"knowledge.search\"")
  end

  def test_a_search_through_the_call_counts_too
    assert Searching.in_source?("call.search(q)")
  end

  def test_a_class_that_never_searches_declares_nothing_about_it
    refute Pinecall::Agent.wire_config.key?(:uses_knowledge)
  end
end
