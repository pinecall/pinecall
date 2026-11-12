# frozen_string_literal: true

module Pinecall
  # The asking of one call: a tool that stops to ask has its call answered with the question, and
  # goes on, on its own thread, once the tool that gives the answer is called. One question at a time.
  class Asking
    NOT_IN_A_TOOL = "ask is for inside a tool: the tool's call is what the question is answered on"

    # What a tool stopped to ask for, for a screen that draws it as a form.
    Asked = Data.define(:task, :asks, :fields, :refused)

    # One tool running on its thread: its name, and where it says it finished, raised or asked.
    Frame = Data.define(:tool, :said)

    # The task one tool waits for, and where its answer is handed to it.
    Waiting = Data.define(:task, :frame, :answer)

    attr_reader :tasks

    # The tasks a call may ask for: its class's, and with a team every member's, once each.
    def self.tasks_on(klass, team = nil) = (team.nil? ? [klass] : team.keys).flat_map(&:declared_tasks).uniq

    # The tools a set of tasks is given with; a name an agent's own tool has is refused.
    def self.giving_tools(tasks, taken)
      clash = tasks.find { |asked| taken.include?(Tasks.given_with(asked)) }
      unless clash.nil?
        raise DeclarationRefused, "the task #{clash.name} is given with #{Tasks.given_with(clash)}, and an agent declares a tool of that name"
      end

      tasks.map { |asked| Tasks.giving_tool(asked) }
    end

    def initialize(tasks)
      @tasks = tasks
      @waiting = nil
      @refused = nil
      @lock = Mutex.new
    end

    # The one tool open while something is asked for; nil when nothing is.
    def open = (waiting = @waiting) && Tasks.giving_tool(waiting.task)

    # What is asked for now, or nil.
    def asking
      waiting = @waiting
      return nil if waiting.nil?

      Asked.new(task: waiting.task.name, asks: waiting.task.asks, fields: waiting.task.fields, refused: @refused)
    end

    # Whether a tool of that name gives one of the call's tasks.
    def gives?(tool) = @tasks.any? { |asked| Tasks.given_with(asked) == tool.to_s }

    # Run the tool on a thread of its own: what it returned, or the question it stopped at.
    def run(name, &tool)
      frame = Frame.new(tool: name.to_s, said: Thread::Queue.new)
      Thread.new do
        Fiber[:pinecall_frame] = frame
        frame.said.push([:returned, tool.call])
      rescue StandardError => e
        frame.said.push([:raised, e])
      end
      outcome(frame)
    end

    # Ask for a task from inside a tool: blocks the tool's thread until the answer is given.
    def ask(asked)
      frame = Fiber[:pinecall_frame]
      raise Error, NOT_IN_A_TOOL if frame.nil?
      raise Error, "#{asked.name} is not a task of this agent: name it in tasks" unless @tasks.include?(asked)

      answer = Thread::Queue.new
      @lock.synchronize do
        raise Error, "#{@waiting.task.name} is being asked for: one question at a time" unless @waiting.nil?

        @waiting = Waiting.new(task: asked, frame:, answer:)
      end
      frame.said.push([:asked, Tasks.asking_for(asked)])
      kind, value = answer.pop
      raise value if kind == :dropped

      value
    end

    # The model gave the answer: the waiting tool goes on, and this call says how it ended.
    def given(tool, arguments)
      waiting = @waiting
      raise ToolFailed, "#{tool}: nothing is being asked for with it now" if waiting.nil? || Tasks.given_with(waiting.task) != tool.to_s

      given = arguments.to_h { |key, value| [key.to_s, value] }
      missing = waiting.task.fields.keys.reject { |field| given[field].is_a?(String) }
      raise ToolFailed, "#{tool}: #{missing.join(", ")} must be given, in words" unless missing.empty?

      value = checked(waiting.task, given.slice(*waiting.task.fields.keys))
      @lock.synchronize { @waiting = nil }
      @refused = nil
      waiting.answer.push([:given, value])
      ended = outcome(waiting.frame)
      ended.is_a?(String) ? ended : { finished: waiting.frame.tool, result: ended }
    end

    # The caller's page gave the answer: what the model is to be told, or nil.
    def given_by_page(task, values)
      waiting = @waiting
      return nil if waiting.nil? || waiting.task.name != task.to_s || !values.is_a?(Hash)

      ended = given(Tasks.given_with(waiting.task), values)
      what = waiting.task.asks
      return "The caller gave #{what} on their screen. #{ended}" if ended.is_a?(String)

      "The caller gave #{what} on their screen, and #{waiting.frame.tool} is done with this result: #{JSON.generate(ended[:result])}. Tell them how it went."
    rescue ToolFailed => e
      @refused = e.message
      nil
    end

    # The call ended with a question open: the tool that asked is told.
    def abandon
      waiting = @lock.synchronize { @waiting.tap { @waiting = nil } }
      return if waiting.nil?

      waiting.answer.push([:dropped, Error.new("the call ended before the caller gave #{waiting.task.asks}")])
    end

    private

    # What the tool's thread said next: its result, its question, or what it raised.
    def outcome(frame)
      kind, value = frame.said.pop
      raise value if kind == :raised

      value
    end

    def checked(task, given)
      task.check.call(given)
    rescue StandardError => e
      raise ToolFailed, e.message
    end
  end
end
