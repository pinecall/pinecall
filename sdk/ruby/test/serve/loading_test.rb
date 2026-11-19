# frozen_string_literal: true

require "test_helper"
require "fileutils"
require "tmpdir"

# What the serve entry is told and loads: a file with the slug at its place and the callers of its test folder, a
# state field by field, no flag of its own.
class LoadingTest < Minitest::Test
  Loading = Pinecall::Serve::Loading

  def test_each_file_is_paired_with_the_slug_at_its_place
    flags = Loading.parse(%w[--file a.rb --slug a --file b.rb --slug b --console --events])

    assert_equal [%w[a.rb a], %w[b.rb b]], flags.served.map { |one| [one.file, one.slug] }
    assert flags.console
    assert flags.events
  end

  def test_a_file_without_its_slug_is_refused
    error = assert_raises(Pinecall::Serve::CannotServe) { Loading.parse(%w[--file a.rb]) }
    assert_includes error.message, "one --slug for each --file"
  end

  def test_a_state_is_read_field_by_field_as_json_and_a_value_that_is_not_json_is_refused
    flags = Loading.parse(["--file", "a.rb", "--slug", "a", "--state", 'patient={"name":"Ana"}', "--state", "slots=[]"])

    assert_equal({ patient: { name: "Ana" }, slots: [] }, flags.state)
    error = assert_raises(Pinecall::Serve::CannotServe) { Loading.as_state("patient={nope") }
    assert_equal "--state patient: its value is not JSON", error.message
  end

  def test_a_class_is_served_as_its_folders_slug_and_reads_the_view_named_by_it
    Dir.mktmpdir do |root|
      folder = File.join(root, "agents", "clinic-front-desk")
      FileUtils.mkdir_p(File.join(folder, "views"))
      File.write(File.join(folder, "agent.rb"), "# You answer the phone.\nclass NamedOtherThanItsFolder < Pinecall::Agent\nend\n")
      File.write(File.join(folder, "views", "clinic-front-desk.erb"), "Offer only the open times.\n")
      served = Loading.load_served(Pinecall::Serve::Served.new(file: File.join(folder, "agent.rb"), slug: "clinic-front-desk"))

      assert_equal "clinic-front-desk", served.slug
      assert_equal File.join(folder, "views", "clinic-front-desk.erb"), served.view&.path
    end
  end

  # An agent staged as the CLI lays it out, with what its `test/personas.rb` says when it has one.
  def staged(root, slug, agent, personas = nil)
    folder = File.join(root, "agents", slug)
    FileUtils.mkdir_p(File.join(folder, "test"))
    File.write(File.join(folder, "agent.rb"), agent)
    File.write(File.join(folder, "test", "personas.rb"), personas) unless personas.nil?
    Pinecall::Serve::Served.new(file: File.join(folder, "agent.rb"), slug:)
  end

  def test_the_callers_in_its_test_folder_are_what_the_class_declares_and_none_is_a_constant_of_the_process
    Dir.mktmpdir do |root|
      one = staged(root, "tested-one", "# You answer the phone.\nclass TestedByItsFolderOne < Pinecall::Agent\nend\n", <<~RUBY)
        # frozen_string_literal: true

        require "pinecall"
        require_relative "words"

        ON = %w[in-a-hurry].freeze
        ROSTER_OF_ONE = Pinecall.own_persona(name: "hurried", goal: GOAL_OF_ONE, style: "short sentences")
      RUBY
      File.write(File.join(root, "agents", "tested-one", "test", "words.rb"), "GOAL_OF_ONE = \"a cleaning on Thursday\"\n")
      other = staged(root, "tested-other", "# You answer the phone.\nclass TestedByItsFolderOther < Pinecall::Agent\nend\n", <<~RUBY)
        ON = %w[wrong-number].freeze
        ROSTER_OF_ONE = Pinecall.own_persona(name: "charged-twice", goal: "one charge back", style: "annoyed")
      RUBY
      first, second = Loading.load_served(one), Loading.load_served(other)

      assert_equal({ on: ["in-a-hurry"], own: [{ name: "hurried", goal: "a cleaning on Thursday", style: "short sentences" }] },
                   first.wire_config(tools: [])[:personas])
      assert_equal({ on: ["wrong-number"], own: [{ name: "charged-twice", goal: "one charge back", style: "annoyed" }] },
                   second.wire_config(tools: [])[:personas])
      refute Object.const_defined?(:ROSTER_OF_ONE)
      refute Object.const_defined?(:ON)
    end
  end

  def test_a_class_with_no_such_file_is_tested_with_what_it_names_or_with_nothing
    Dir.mktmpdir do |root|
      names = staged(root, "names-them", <<~RUBY)
        # You answer the phone.
        class NamesItsCallersWithNoFile < Pinecall::Agent
          personas on: %w[in-a-hurry], own: [Pinecall.own_persona(name: "hurried", goal: "book today", style: "short")]
        end
      RUBY
      silent = staged(root, "names-none", "# You answer the phone.\nclass NamesNoCallerAndHasNoFile < Pinecall::Agent\nend\n")
      named, quiet = Loading.load_served(names), Loading.load_served(silent)

      assert_nil named.tested_with
      assert_equal({ on: ["in-a-hurry"], own: [{ name: "hurried", goal: "book today", style: "short" }] }, named.wire_config(tools: [])[:personas])
      assert_nil quiet.tested_with
      refute quiet.wire_config(tools: []).key?(:personas)
    end
  end

  def test_a_class_that_names_its_personas_beside_the_file_is_refused_naming_both
    Dir.mktmpdir do |root|
      both = staged(root, "names-both", <<~AGENT, "ON = %w[in-a-hurry].freeze\n")
        # You answer the phone.
        class NamesItsCallersBesideTheFile < Pinecall::Agent
          personas on: %w[wrong-number]
        end
      AGENT
      error = assert_raises(Pinecall::DeclarationRefused) { Loading.load_served(both) }

      assert_equal "NamesItsCallersBesideTheFile declares personas in the class and " \
                   "#{File.join(root, "agents", "names-both", "test", "personas.rb")} holds them too: " \
                   "the file is their place — take personas out of the class", error.message
    end
  end

  def test_a_file_of_callers_that_is_wrong_is_refused_by_its_sentence_and_one_that_does_not_load_by_its_path
    Dir.mktmpdir do |root|
      agent = "# You answer the phone.\nclass %s < Pinecall::Agent\nend\n"
      goalless = staged(root, "goalless", format(agent, "TestedByAGoallessCaller"),
                        "RUSH = Pinecall.own_persona(name: \"in-a-rush\", goal: \" \", style: \"short\")\n")
      unnamed = staged(root, "unnamed", format(agent, "TestedByAnOnThatIsNoList"), "ON = \"in-a-hurry\"\n")
      broken = staged(root, "broken", format(agent, "TestedByAFileThatDoesNotLoad"), "ON = %w[in-a-hurry\nRUSH = NoSuchConstantAnywhere\n")

      error = assert_raises(Pinecall::DeclarationRefused) { Loading.load_served(goalless) }
      assert_equal "in-a-rush: a persona wants something: write its goal, in the first person", error.message
      error = assert_raises(Pinecall::DeclarationRefused) { Loading.load_served(unnamed) }
      assert_includes error.message, "test/personas.rb: ON is the names of Pinecall's callers the agent is tested with, an array of strings"
      error = assert_raises(Pinecall::Serve::CannotServe) { Loading.load_served(broken) }
      assert_includes error.message, "#{File.join(root, "agents", "broken", "test", "personas.rb")} did not load: "
    end
  end

  def test_a_flag_it_does_not_have_is_refused_by_name
    error = assert_raises(Pinecall::Serve::CannotServe) { Loading.parse(%w[--file a.rb --slug a --fast]) }
    assert_equal "serve has no flag --fast", error.message
  end
end
