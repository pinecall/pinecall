# frozen_string_literal: true

require "stringio"
require "tmpdir"
require "test_helper"
require_relative "client/fake_gateway"

# The entry the one CLI starts a Ruby agent with: the wire on stdout, its door from the environment,
# a drained leave, and a prompt that needs nothing.
class ServeTest < Minitest::Test
  AGENT = File.expand_path("../../../examples/ruby/clinica_norte/agents/clinica-norte/agent.rb", __dir__)
  SLUG = "clinica-norte"

  def setup
    @gateway = FakeGateway.new
    @out = StringIO.new
    @err = StringIO.new
  end

  def teardown = @gateway.stop

  def env(**more) = { "PINECALL_URL" => @gateway.url, "PINECALL_KEY" => "pk_test" }.merge(more)

  # `start` on a thread, its stdin a pipe the test holds and its signals a queue the test pushes.
  def started(*flags, environment: env)
    reading, @writing = IO.pipe
    @signals = Thread::Queue.new
    Thread.new do
      Pinecall::Serve.main(["start", "--file", AGENT, "--slug", SLUG, *flags], out: @out, err: @err, env: environment,
                                                                              input: reading, signals: @signals)
    end
  end

  def until_registered
    refute_nil @gateway.next_frame("agent.configure")
    sleep(0.05)
  end

  def test_the_first_line_is_the_registration_with_the_app_it_was_given
    running = started("--events")
    until_registered
    @signals.push(:signalled)

    assert_equal 0, running.value
    first = JSON.parse(@out.string.lines.first, symbolize_names: true)
    assert_equal({ type: "agent.registered", agent: SLUG, call: nil }, first.slice(:type, :agent, :call))
    assert_equal "app_1", first[:data][:app]
  end

  def test_on_a_pipe_the_registration_is_read_while_the_process_still_holds
    piped, @out = IO.pipe
    @out.sync = false # as $stdout is when it is not a terminal
    running = started("--events")
    seen = Thread.new { piped.gets }.join(5)&.value
    @signals.push(:signalled)
    running.join(5)

    refute_nil seen, "nothing reached the pipe before the process left"
    assert_equal "agent.registered", JSON.parse(seen)["type"]
  ensure
    @out.close unless @out.closed?
    piped&.close
  end

  def test_a_signal_drains_before_the_socket_closes
    running = started
    until_registered
    @signals.push(:signalled)

    assert_equal 0, running.value
    refute_nil @gateway.next_frame("agent.drain")
    assert_includes @err.string, "draining · no live calls"
  end

  def test_a_signal_and_then_the_end_of_its_stdin_is_one_ask_and_it_drains_whole
    running = started
    until_registered
    @signals.push(:signalled)
    @writing.close # the CLI passes a signal on and closes the pipe, both at once

    assert_equal 0, running.value
    refute_nil @gateway.next_frame("agent.drain")
    assert_includes @err.string, "draining · no live calls"
  end

  def test_a_second_signal_leaves_without_waiting_for_the_drain
    @gateway.answers_drains = false
    running = started
    until_registered
    @signals.push(:signalled)
    refute_nil @gateway.next_frame("agent.drain")
    @signals.push(:signalled)

    assert_equal 0, running.join(5)&.value
    refute_includes @err.string, "draining"
  end

  def test_the_end_of_its_stdin_drains_it_too
    running = started
    until_registered
    @writing.close

    assert_equal 0, running.value
    refute_nil @gateway.next_frame("agent.drain")
  end

  def test_a_consoles_process_takes_no_unclaimed_call_and_prod_names_production
    running = started("--console", "--prod")
    registered = @gateway.next_frame("agent.register")
    until_registered
    @signals.push(:signalled)
    running.value

    assert_equal false, registered[:data][:takes_unclaimed]
    assert_equal "production", @gateway.world
  end

  def test_the_console_is_answered_its_panel_by_the_class_and_every_other_verb_is_the_clis
    Dir.mktmpdir do |folder|
      file = File.join(folder, "agent.rb")
      File.write(file, <<~RUBY)
        # La ficha, en la consola.
        class ConFicha < Pinecall::Agent
          panel "Ficha" do |who|
            panel "Paciente" do
              row "Teléfono", who.contact
            end
          end
        end
      RUBY
      reading, @writing = IO.pipe
      running = Thread.new do
        Pinecall::Serve.main(["start", "--file", file, "--slug", "con-ficha"], out: @out, err: @err, env:, input: reading,
                                                                                signals: Thread::Queue.new)
      end
      until_registered
      @gateway.send_entry("con-ficha", "dev.request", { id: "dev_1", verb: "view.render", data: { contact: "+34600", call: "CA_1" } })
      @gateway.send_entry("con-ficha", "dev.request", { id: "dev_2", verb: "goldens.roster", data: {} })
      answers = [@gateway.next_frame("dev.answer"), @gateway.next_frame("dev.answer")].map { |frame| frame[:data] }
      @writing.close
      running.value

      panel = { tag: "panel", title: "Paciente", children: [{ tag: "row", label: "Teléfono", value: "+34600" }] }
      assert_includes answers, { id: "dev_1", result: { name: "Ficha", nodes: [panel] } }
      assert_includes answers, { id: "dev_2", refused: { status: 404, detail: Pinecall::Serve::Viewing::ONLY_THE_VIEW } }
    end
  end

  def test_a_class_that_draws_no_panel_is_a_404_the_console_falls_back_from
    running = started
    until_registered
    @gateway.send_entry(SLUG, "dev.request", { id: "dev_1", verb: "view.render", data: { contact: "+34600", call: "CA_1" } })
    answer = @gateway.next_frame("dev.answer")[:data]
    @writing.close
    running.value

    assert_equal({ id: "dev_1", refused: { status: 404, detail: "#{SLUG} declares no view: nothing in this directory draws a panel" } },
                 answer)
  end

  def test_nothing_in_the_environment_is_a_sentence_and_exit_two
    code = Pinecall::Serve.main(["start", "--file", AGENT, "--slug", SLUG], out: @out, err: @err, env: {})

    assert_equal 2, code
    assert_includes @err.string, "PINECALL_URL and PINECALL_KEY"
  end

  def test_a_registration_the_gateway_refuses_is_a_sentence_and_exit_two
    @gateway.taken = [SLUG]

    code = Pinecall::Serve.main(["start", "--file", AGENT, "--slug", SLUG], out: @out, err: @err, env: env)

    assert_equal 2, code
    assert_includes @err.string, "agent #{SLUG} belongs to another org"
    refute_includes @err.string, "block in"
  end

  def test_a_gateway_that_is_not_there_is_a_sentence_and_exit_two
    code = Pinecall::Serve.main(["start", "--file", AGENT, "--slug", SLUG], out: @out, err: @err,
                                                                            env: env("PINECALL_URL" => "http://127.0.0.1:1"))

    assert_equal 2, code
    assert_includes @err.string, "127.0.0.1:1"
  end

  def test_a_prompt_needs_no_gateway_and_opens_in_the_state_its_pairs_name
    code = Pinecall::Serve.main(["prompt", "--file", AGENT, "--slug", SLUG, "--state", 'stage="book"',
                                 "--state", 'patient={"name":"Ana García"}', "--show-machine"], out: @out, err: @err, env: {})

    assert_equal 0, code
    assert_includes @out.string, "── tools ── stage: book"
  end

  def test_a_prompt_writes_for_the_channel_and_medium_it_is_asked_for
    code = Pinecall::Serve.main(["prompt", "--file", AGENT, "--slug", SLUG, "--channel", "web", "--medium", "text"],
                                out: @out, err: @err, env: {})

    assert_equal 0, code
    assert_includes @out.string, "<channel>\n#{Pinecall::Rules::ON_A_WEBSITE}\n</channel>"
    assert_equal 2, Pinecall::Serve.main(["prompt", "--file", AGENT, "--slug", SLUG, "--medium", "fax"], out: @out, err: @err)
    assert_includes @err.string, "--medium is voice or text"
  end

  def test_a_file_with_no_agent_and_a_verb_nobody_wrote_are_refused
    assert_equal 2, Pinecall::Serve.main(["prompt", "--file", "nowhere.rb", "--slug", SLUG], out: @out, err: @err)
    assert_includes @err.string, "no agent at"
    assert_equal 2, Pinecall::Serve.main(["fly"], out: @out, err: @err)
  end

  def test_a_class_whose_own_slug_is_another_is_refused
    Dir.mktmpdir do |folder|
      file = File.join(folder, "agent.rb")
      File.write(file, "# Otra.\nclass OtraServida < Pinecall::Agent\n  slug \"otra\"\nend\n")

      assert_equal 2, Pinecall::Serve.main(["prompt", "--file", file, "--slug", "una"], out: @out, err: @err)
      assert_includes @err.string, "says its slug is otra, and it is served as una"
    end
  end
end
