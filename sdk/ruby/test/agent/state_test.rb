# frozen_string_literal: true

require "test_helper"

class StateTest < Minitest::Test
  # Una tienda que recuerda un carrito.
  class Tienda < Pinecall::Agent
    stage :browsing, :checkout
    state :cart, []
    state :customer
    state(:has_cart) { cart.any? }

    # Añade una línea al carrito.
    tool
    def add(item:)
      self.cart = cart + [item]
      self.stage = :checkout
      cart
    end
  end

  def setup
    @agent = Tienda.new.seal
  end

  def test_a_field_starts_at_the_value_the_class_gave_it
    assert_equal [], @agent.cart
    assert_equal :browsing, @agent.stage
    assert_nil @agent.customer
  end

  def test_every_call_gets_a_list_of_its_own_and_not_one_shared_by_all_of_them
    @agent.run_tool(:add, item: "café")
    other = Tienda.new.seal

    assert_equal [], other.cart
  end

  def test_a_write_outside_a_tool_is_refused_by_name
    refused = assert_raises(Pinecall::UnauthoredWrite) { @agent.customer = "Marta" }

    assert_includes refused.message, "customer"
  end

  def test_a_write_inside_a_tool_carries_the_tool_s_own_name
    @agent.run_tool(:add, item: "café")

    assert_equal %w[add add], @agent.changes.map(&:author)
    assert_equal %i[cart stage], @agent.changes.map(&:field)
  end

  def test_the_opening_values_are_the_baseline_and_not_a_change
    assert_empty Tienda.new.seal.changes
  end

  def test_assigning_the_same_value_again_is_not_a_change
    @agent.run_tool(:add, item: "café")
    Pinecall::Agent::Author.with("by hand") { @agent.cart = ["café"] }

    assert_equal 2, @agent.changes.size
  end

  def test_a_derived_field_is_state_and_cannot_be_assigned
    assert_includes @agent.snapshot.keys, :has_cart
    refute @agent.snapshot[:has_cart]
    refute_respond_to @agent, :has_cart=
  end

  def test_a_snapshot_is_the_state_and_nothing_the_class_configured
    @agent.run_tool(:add, item: "café")

    assert_equal({ cart: ["café"], customer: nil, stage: :checkout, has_cart: true }, @agent.snapshot)
  end

  def test_restoring_a_snapshot_clears_a_field_the_snapshot_leaves_out
    @agent.run_tool(:add, item: "café")
    @agent.restore({ stage: :browsing })

    assert_nil @agent.cart
    assert_equal :browsing, @agent.stage
  end

  def test_starting_in_a_state_names_what_it_is_about_and_keeps_the_rest
    @agent.start_in({ customer: "Marta" })

    assert_equal "Marta", @agent.customer
    assert_equal [], @agent.cart
  end

  def test_collapsing_keeps_one_sentence_where_the_changes_were
    @agent.run_tool(:add, item: "café")
    @agent.collapse("El cliente pidió un café.")

    assert_equal 1, @agent.changes.size
    assert_equal "@summary", @agent.changes.first.field
    assert_equal ["café"], @agent.cart
  end

  def test_two_agents_writing_at_once_never_read_each_other_s_author
    seen = Queue.new
    threads = %w[one two].map do |name|
      Thread.new do
        Pinecall::Agent::Author.with(name) do
          sleep(0.01)
          seen << [name, Pinecall::Agent::Author.current]
        end
      end
    end
    threads.each(&:join)

    assert_equal [%w[one one], %w[two two]], Array.new(2) { seen.pop }.sort
  end

  def test_declaring_one_name_twice_is_refused_at_load
    assert_raises(Pinecall::DeclarationRefused) do
      Class.new(Pinecall::Agent) do
        state :cart
        state :cart
      end
    end
  end
end
