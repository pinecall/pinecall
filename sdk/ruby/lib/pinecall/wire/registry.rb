# frozen_string_literal: true

# Every event and command of the wire by its type, and the shape its data is.

require "set"

module Pinecall
  module Wire
    module Registry
      # The shape each event's data is, by the event's wire type.
      EVENTS = {
        "agent.configured" => "AgentConfigured",
        "agent.detached" => "AgentDetached",
        "agent.draining" => "AgentDraining",
        "agent.registered" => "AgentRegistered",
        "agent.state" => "AgentStateChanged",
        "agent.transcript" => "AgentTranscript",
        "attention.answered" => "AttentionAnswered",
        "attention.requested" => "AttentionRequested",
        "call.attached" => "CallAttached",
        "call.claimed" => "CallClaimed",
        "call.dialing" => "CallDialing",
        "call.ended" => "CallEnded",
        "call.line" => "CallLine",
        "call.ringing" => "CallRinging",
        "call.score" => "CallScore",
        "call.started" => "CallStarted",
        "call.summary" => "CallSummary",
        "call.transferred" => "CallTransferred",
        "callback.requested" => "CallbackRequested",
        "code.claimed" => "CodeClaimed",
        "code.issued" => "CodeIssued",
        "confirm.declined" => "ConfirmDeclined",
        "confirm.granted" => "ConfirmGranted",
        "confirm.request" => "ConfirmRequest",
        "credits.exhausted" => "CreditsExhausted",
        "evals.spent" => "EvalsSpent",
        "custom" => "Custom",
        "dev.request" => "DevRequest",
        "docs.sources" => "DocsSources",
        "dtmf.received" => "DtmfReceived",
        "error" => "ErrorEvent",
        "event.received" => "EventReceived",
        "fleet.full" => "FleetFull",
        "judge.broke" => "JudgeBroke",
        "log.caught_up" => "LogCaughtUp",
        "log.gap" => "LogGap",
        "memory.ops" => "MemoryOps",
        "message.taken" => "MessageTaken",
        "message.waiting" => "MessageWaiting",
        "metrics.avatar" => "AvatarMetrics",
        "metrics.eot" => "EOTInferenceMetrics",
        "metrics.eou" => "EOUMetrics",
        "metrics.interruption" => "InterruptionMetrics",
        "metrics.llm" => "LLMMetrics",
        "metrics.realtime" => "RealtimeModelMetrics",
        "metrics.stt" => "STTMetrics",
        "metrics.tts" => "TTSMetrics",
        "metrics.vad" => "VADMetrics",
        "participant.joined" => "ParticipantJoined",
        "participant.left" => "ParticipantLeft",
        "participant.speaking" => "ParticipantSpeaking",
        "pong" => "Pong",
        "prompt.changed" => "PromptChanged",
        "release.changed" => "ReleaseChanged",
        "room.opened" => "RoomOpened",
        "room.sent" => "RoomSent",
        "run.changed" => "RunChanged",
        "spend.unusual" => "SpendUnusual",
        "state.changed" => "StateChanged",
        "supervisor.ended" => "SupervisorEnded",
        "supervisor.released" => "SupervisorReleased",
        "supervisor.said" => "SupervisorSaid",
        "supervisor.took_over" => "SupervisorTookOver",
        "supervisor.transferred" => "SupervisorTransferred",
        "supervisor.whispered" => "SupervisorWhispered",
        "tool.call" => "ToolCall",
        "tool.failed" => "ToolFailed",
        "tool.ran" => "ToolRan",
        "tool.result" => "ToolResult",
        "tools.changed" => "ToolsChanged",
        "track.published" => "TrackPublished",
        "track.unpublished" => "TrackUnpublished",
        "turn.agent" => "AgentTurnEnded",
        "turn.user" => "UserTurnEnded",
        "user.state" => "UserStateChanged",
        "user.transcript" => "UserTranscript",
        "vendor.switched" => "VendorSwitched",
        "worker.changed" => "WorkerChanged"
      }.freeze

      # The shape each command's data is, by the command's wire type.
      COMMANDS = {
        "agent.configure" => "AgentConfigure",
        "agent.drain" => "AgentDrain",
        "agent.register" => "AgentRegister",
        "agent.reply" => "AgentReply",
        "agent.say" => "AgentSay",
        "call.attention" => "CallAttention",
        "call.callback" => "CallCallback",
        "call.claim" => "CallClaim",
        "call.dial" => "CallDial",
        "call.dtmf" => "CallDtmf",
        "call.event" => "CallEvent",
        "call.hangup" => "CallHangup",
        "call.hold" => "CallHold",
        "call.log" => "CallLog",
        "call.mute" => "CallMute",
        "call.opt_out" => "CallOptOut",
        "call.transfer" => "CallTransfer",
        "call.unhold" => "CallUnhold",
        "call.unmute" => "CallUnmute",
        "dev.answer" => "DevAnswer",
        "participant.mute" => "ParticipantMute",
        "participant.remove" => "ParticipantRemove",
        "ping" => "Ping",
        "prompt.set" => "PromptSet",
        "room.invite" => "RoomInvite",
        "room.send" => "RoomSend",
        "session.configure" => "SessionConfigure",
        "state.set" => "StateSet",
        "supervisor.verb" => "SupervisorVerb",
        "tool.result" => "ToolResult",
        "tools.set" => "ToolsSet"
      }.freeze

      # Every event this protocol declares, in the schema's own order.
      EVENT_TYPES = %w[agent.configured agent.detached agent.draining agent.registered agent.state agent.transcript attention.answered attention.requested call.attached call.claimed call.dialing call.ended call.line call.ringing call.score call.started call.summary call.transferred callback.requested code.claimed code.issued confirm.declined confirm.granted confirm.request credits.exhausted custom dev.request docs.sources dtmf.received error evals.spent event.received fleet.full judge.broke log.caught_up log.gap memory.ops message.taken message.waiting metrics.avatar metrics.eot metrics.eou metrics.interruption metrics.llm metrics.realtime metrics.stt metrics.tts metrics.vad participant.joined participant.left participant.speaking pong prompt.changed release.changed room.opened room.sent run.changed spend.unusual state.changed supervisor.ended supervisor.released supervisor.said supervisor.took_over supervisor.transferred supervisor.whispered tool.call tool.failed tool.ran tool.result tools.changed track.published track.unpublished turn.agent turn.user user.state user.transcript vendor.switched worker.changed].freeze

      # Every command an app may send.
      COMMAND_TYPES = %w[agent.configure agent.drain agent.register agent.reply agent.say call.attention call.callback call.claim call.dial call.dtmf call.event call.hangup call.hold call.log call.mute call.opt_out call.transfer call.unhold call.unmute dev.answer participant.mute participant.remove ping prompt.set room.invite room.send session.configure state.set supervisor.verb tool.result tools.set].freeze

      # Entries a store may drop and a slow reader may miss without harm: the entry's
      # own ephemeral flag defaults to this.
      EPHEMERAL_EVENTS = %w[agent.transcript dev.request judge.broke log.caught_up log.gap metrics.vad participant.speaking pong release.changed room.sent run.changed tool.failed tool.ran user.transcript worker.changed].to_set.freeze

      # The one event that ends a call: after it nothing more is true and the log seals.
      TERMINAL_EVENT = "call.score"

      # Which events a command lands in the log as, so a caller knows what to wait for.
      PRODUCES = {
        "agent.configure" => %w[agent.configured],
        "agent.drain" => %w[agent.draining],
        "agent.register" => %w[agent.registered],
        "agent.reply" => %w[turn.agent],
        "agent.say" => %w[turn.agent],
        "call.attention" => %w[attention.requested call.line attention.answered],
        "call.callback" => %w[callback.requested],
        "call.claim" => %w[call.claimed],
        "call.dial" => %w[call.dialing],
        "call.dtmf" => [],
        "call.event" => %w[event.received],
        "call.hangup" => %w[call.ended],
        "call.hold" => %w[call.line],
        "call.log" => %w[custom],
        "call.mute" => %w[call.line],
        "call.transfer" => %w[call.transferred],
        "call.unhold" => %w[call.line],
        "call.unmute" => %w[call.line],
        "dev.answer" => [],
        "participant.mute" => %w[track.unpublished],
        "participant.remove" => %w[participant.left],
        "ping" => %w[pong],
        "prompt.set" => %w[prompt.changed],
        "room.invite" => %w[participant.joined],
        "room.send" => %w[room.sent],
        "session.configure" => %w[state.changed agent.configured],
        "state.set" => %w[state.changed],
        "supervisor.verb" => %w[supervisor.said supervisor.whispered supervisor.took_over supervisor.released supervisor.transferred supervisor.ended],
        "tool.result" => %w[tool.result],
        "tools.set" => %w[tools.changed]
      }.freeze
    end
  end
end
