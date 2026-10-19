# frozen_string_literal: true

require "test_helper"

# Every command of this gem's wire is sent by one method of the SDK or said to be nobody's here, and
# every event is folded by a part of it or ignored with a reason. A new wire entry fails here, by name.
class ConformanceTest < Minitest::Test
  LIB = File.expand_path("../lib/pinecall", __dir__)

  # The method that sends each command.
  COMMANDS = {
    "agent.say" => "Pinecall::CallWorld#say",
    "agent.reply" => "Pinecall::CallWorld#reply",
    "room.send" => "Pinecall::CallWorld#send_to",
    "room.invite" => "Pinecall::CallWorld#invite",
    "participant.mute" => "Pinecall::CallWorld::Seat#mute",
    "participant.remove" => "Pinecall::CallWorld::Seat#remove",
    "call.log" => "Pinecall::CallWorld#log",
    "call.hangup" => "Pinecall::CallWorld#hangup",
    "call.opt_out" => "Pinecall::CallWorld#opt_out",
    "call.transfer" => "Pinecall::CallWorld#transfer",
    "call.attention" => "Pinecall::CallWorld#attention",
    "call.hold" => "Pinecall::CallWorld#hold",
    "call.unhold" => "Pinecall::CallWorld#unhold",
    "call.dtmf" => "Pinecall::CallWorld#dtmf",
    "call.claim" => "Pinecall::CallWorld#claim",
    "call.callback" => "Pinecall::CallWorld#callback",
    "prompt.set" => "Pinecall::Client::Call#set_prompt",
    "tools.set" => "Pinecall::Client::Call#set_tools",
    "state.set" => "Pinecall::Client::Call#set_state",
    "tool.result" => "Pinecall::Client::Call#tool_result",
    "call.event" => "Pinecall::Client::Call#event",
    "agent.register" => "Pinecall::Client::Agent#open",
    "agent.configure" => "Pinecall::Client::Agent#configure",
    "agent.drain" => "Pinecall::Client::Agent#drain",
    "ping" => "Pinecall::Client::Agent#ping"
  }.freeze

  # Commands no SDK method sends, and whose they are.
  NOT_THE_SDKS = {
    "call.dial" => "a call is placed through POST /v1/calls; the app socket refuses it",
    "call.mute" => "the desk's: a supervisor mutes the agent",
    "call.unmute" => "the desk's: a supervisor unmutes the agent",
    "session.configure" => "the gateway's own, for a declaration it makes for one call",
    "supervisor.verb" => "the desk's: a supervisor's socket, never an app's",
    "dev.answer" => "the client's default answer to a console, never a method an app calls"
  }.freeze

  # The files that fold each event this SDK acts on.
  FOLDED = {
    "participant.joined" => %i[call_world],
    "participant.left" => %i[call_world],
    "participant.speaking" => %i[call_world],
    "turn.user" => %i[call_world],
    "turn.agent" => %i[call_world],
    "call.claimed" => %i[call_world client_call],
    "call.transferred" => %i[call_world],
    "attention.answered" => %i[call_world],
    "call.ended" => %i[call_world bridge client_call],
    "event.received" => %i[bridge],
    "memory.ops" => %i[bridge],
    "call.attached" => %i[bridge client_call],
    "call.started" => %i[bridge client_call],
    "call.ringing" => %i[client_call],
    "call.dialing" => %i[client_call],
    "state.changed" => %i[client_call],
    "agent.registered" => %i[client_agent],
    "agent.configured" => %i[client_agent],
    "agent.draining" => %i[client_agent],
    "error" => %i[client_agent],
    "tool.call" => %i[client_agent],
    "dev.request" => %i[client_agent]
  }.freeze

  A_MEASURE = "a measure for the console and the evals; an app reads it with call.on"
  THE_DESKS = "what a supervisor did, for the desk; an app reads it with call.on"
  THE_LOGS = "the log's own bookkeeping, for a reader of the log"
  THE_GATEWAYS = "the gateway's record of the call, read by the console and the judges"

  # Events this SDK leaves to `call.on` and `client.on_any`, and why.
  IGNORED = {
    "agent.detached" => "the gateway's record that a socket let the agent go",
    "agent.state" => THE_GATEWAYS,
    "agent.transcript" => "a partial line, for a live screen",
    "user.transcript" => "a partial line, for a live screen",
    "user.state" => THE_GATEWAYS,
    "attention.requested" => THE_GATEWAYS,
    "call.line" => THE_GATEWAYS,
    "call.score" => THE_GATEWAYS,
    "call.summary" => THE_GATEWAYS,
    "callback.requested" => THE_GATEWAYS,
    "code.claimed" => THE_GATEWAYS,
    "code.issued" => THE_GATEWAYS,
    "confirm.request" => THE_GATEWAYS,
    "confirm.granted" => THE_GATEWAYS,
    "confirm.declined" => THE_GATEWAYS,
    "credits.exhausted" => THE_GATEWAYS,
    "evals.spent" => THE_GATEWAYS,
    "spend.unusual" => THE_GATEWAYS,
    "vendor.switched" => THE_GATEWAYS,
    "custom" => "an app's own entry, read back by whoever wrote it",
    "docs.sources" => THE_GATEWAYS,
    "dtmf.received" => "a tone the caller keyed; an app that reads a menu takes it with call.on",
    "fleet.full" => THE_GATEWAYS,
    "release.changed" => THE_GATEWAYS,
    "run.changed" => THE_GATEWAYS,
    "tool.ran" => THE_GATEWAYS,
    "tool.failed" => THE_GATEWAYS,
    "judge.broke" => THE_GATEWAYS,
    "worker.changed" => THE_GATEWAYS,
    "message.taken" => THE_GATEWAYS,
    "message.waiting" => THE_GATEWAYS,
    "prompt.changed" => THE_GATEWAYS,
    "tools.changed" => THE_GATEWAYS,
    "room.opened" => THE_GATEWAYS,
    "room.sent" => THE_GATEWAYS,
    "track.published" => THE_GATEWAYS,
    "track.unpublished" => THE_GATEWAYS,
    "log.caught_up" => THE_LOGS,
    "log.gap" => THE_LOGS,
    "pong" => "the answer to ping, which keeps the socket warm",
    "tool.result" => "the log's record of an answer this SDK sent",
    "metrics.avatar" => A_MEASURE,
    "metrics.eot" => A_MEASURE,
    "metrics.eou" => A_MEASURE,
    "metrics.interruption" => A_MEASURE,
    "metrics.llm" => A_MEASURE,
    "metrics.realtime" => A_MEASURE,
    "metrics.stt" => A_MEASURE,
    "metrics.tts" => A_MEASURE,
    "metrics.vad" => A_MEASURE,
    "supervisor.ended" => THE_DESKS,
    "supervisor.released" => THE_DESKS,
    "supervisor.said" => THE_DESKS,
    "supervisor.took_over" => THE_DESKS,
    "supervisor.transferred" => THE_DESKS,
    "supervisor.whispered" => THE_DESKS
  }.freeze

  OWNERS = {
    call_world: ["call_world.rb", "call_world/*.rb"],
    bridge: ["bridge.rb"],
    client_call: ["client/call.rb"],
    client_agent: ["client/agent.rb"]
  }.freeze

  def test_every_command_is_sent_by_the_sdk_or_said_to_be_nobodys_here
    strays = Pinecall::Wire::Registry::COMMANDS.keys - COMMANDS.keys - NOT_THE_SDKS.keys
    assert_empty strays, "a command with no owner and no reason: #{strays.join(", ")}"
    unknown = (COMMANDS.keys + NOT_THE_SDKS.keys) - Pinecall::Wire::Registry::COMMANDS.keys
    assert_empty unknown, "a row naming no command of the wire: #{unknown.join(", ")}"
    assert_empty COMMANDS.keys & NOT_THE_SDKS.keys, "a command both owned and nobody's"
  end

  def test_every_command_owned_is_a_method_that_exists
    missing = COMMANDS.reject do |_, owner|
      klass, method = owner.split("#")
      Object.const_get(klass).method_defined?(method.to_sym)
    end
    assert_empty missing.keys, "owned by a method that does not exist: #{missing.values.join(", ")}"
  end

  def test_every_event_is_folded_by_a_part_of_the_sdk_or_ignored_with_a_reason
    strays = Pinecall::Wire::Registry::EVENT_TYPES - FOLDED.keys - IGNORED.keys
    assert_empty strays, "an event with no owner and no reason: #{strays.join(", ")}"
    unknown = (FOLDED.keys + IGNORED.keys) - Pinecall::Wire::Registry::EVENT_TYPES
    assert_empty unknown, "a row naming no event of the wire: #{unknown.join(", ")}"
    assert_empty FOLDED.keys & IGNORED.keys, "an event both folded and ignored"
  end

  def test_every_event_folded_is_read_by_name_in_the_files_that_fold_it
    unread = FOLDED.flat_map do |event, owners|
      owners.reject { |owner| source_of(owner).include?("\"#{event}\"") }.map { |owner| "#{event} in #{owner}" }
    end
    assert_empty unread, "folded by a part that never reads it: #{unread.join(", ")}"
  end

  private

  def source_of(owner)
    OWNERS.fetch(owner).flat_map { |glob| Dir[File.join(LIB, glob)] }.map { |file| File.read(file) }.join
  end
end
