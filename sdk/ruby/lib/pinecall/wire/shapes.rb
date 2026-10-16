# frozen_string_literal: true

# Every named shape of the wire, as the table Validate walks. A shape is closed: a key nobody
# declared is refused by name, since it means the gateway speaks a newer wire than this gem.

require_relative "shapes_parts"
require_relative "shapes_call_events"
require_relative "shapes_events"
require_relative "shapes_commands"
require_relative "shapes_doors"
require_relative "shapes_config"
require_relative "shapes_metrics"

module Pinecall
  module Wire
    module Shapes
      SHAPES = [PARTS, CONFIG, METRICS, CALL_EVENTS, EVENTS, COMMANDS, DOORS].reduce(:merge).freeze

      # A union is told apart by one field, the way the schema's discriminator says.
      UNIONS = {
        "ModelUsage" => { on: :type, members: %w[LLMModelUsage TTSModelUsage STTModelUsage InterruptionModelUsage EOTModelUsage] }.freeze,
        "Turn" => { on: :role, members: %w[UserTurn AgentTurn] }.freeze,
        "Verb" => { on: :verb, members: %w[SayVerb WhisperVerb TakeoverVerb ReleaseVerb TransferVerb EndVerb] }.freeze,
        "StateCause" => { on: :kind, members: %w[StateCauseTool StateCauseEvent] }.freeze
      }.freeze

      # A map is keyed by names the app chose; every value is the one shape given here.
      MAPS = {
        "PromptState" => { kind: :ref, ref: "PromptBlockState" }.freeze
      }.freeze
    end
  end
end
