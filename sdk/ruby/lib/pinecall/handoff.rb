# frozen_string_literal: true

module Pinecall
  # A team of agents one call passes between: the tools that offer the pass, and who answers first.
  # A team is a Hash of each agent class to the slug it is served as.
  module Handoff
    # How many times one call is passed before the next pass is refused.
    MOST_PASSES = 3
    # The custom entry a pass leaves on its call.
    PASSED = "handoff"
    # The custom entry a call leaves when its line's `answers` chose who serves it, or could not.
    ROUTED = "routed"
    # How long a line's `answers` has to choose: the caller is hearing the greeting meanwhile.
    ANSWERED_WITHIN_S = 1.0
    TRANSFER = "transfer_to_"

    # Who serves a call whose line chooses, and why it is not the one chosen, when it is not.
    Answered = Data.define(:agent, :why)

    module_function

    # What `answers` chose when it is of the team and came in time, else `bound`. Never raises.
    def answered_by(answers, line, bound, team)
      chosen = Timeout.timeout(ANSWERED_WITHIN_S) { answers.call(line) }
      return Answered.new(agent: bound, why: nil) if chosen.nil? || chosen == bound
      return Answered.new(agent: bound, why: "answers chose #{chosen}, which is not of the line's team") unless team.key?(chosen)

      Answered.new(agent: chosen, why: nil)
    rescue Timeout::Error
      Answered.new(agent: bound, why: "answers took more than #{ANSWERED_WITHIN_S} s")
    rescue StandardError => e
      Answered.new(agent: bound, why: "answers raised: #{e.message}")
    end

    # The tool a teammate is offered by: named by its class, which the model reads.
    def transfer_name(mate)
      "#{TRANSFER}#{mate.name.split("::").last.gsub(/([a-z0-9])([A-Z])/, '\1_\2').downcase}"
    end

    # The tools that offer a call of `klass` to each teammate that says what it takes.
    def transfers_of(klass, team)
      team.keys.filter_map do |mate|
        takes = mate.declared_takes
        next if mate == klass || takes.nil?

        {
          name: transfer_name(mate),
          description: "Pass the call to #{mate.name.split("::").last}, who takes #{takes}. Call it as soon as the caller brings " \
                       "that up: do not ask them first, and do not answer it yourself. The caller is not told about the pass.",
          parameters: { type: "object", properties: { reason: { type: "string", description: "Why, in a few words." } },
                        required: [] },
          side_effect: "read"
        }
      end
    end

    # The teammate a transfer tool names.
    def mate_named(tool, team) = team.keys.find { |mate| transfer_name(mate) == tool.to_s }

    # Every tool a call of the team may open; a name two members declare is refused.
    def team_tools(team)
      owners = {}
      team.each_with_object([]) do |(member, slug), declared|
        (member.declared_tools.values.map(&:spec) + transfers_of(member, team)).each do |spec|
          owner = owners[spec[:name]]
          next if owner == slug || (!owner.nil? && spec[:name].start_with?(TRANSFER))
          unless owner.nil?
            raise DeclarationRefused, "#{owner} and #{slug} both declare a tool named #{spec[:name]}: the agents of one team give each tool a name of its own"
          end

          owners[spec[:name]] = slug
          declared << spec
        end
      end
    end
  end
end
