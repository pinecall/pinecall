# frozen_string_literal: true

# Every closed list of the wire this gem reads, as a frozen array.

module Pinecall
  module Wire
    module Enums
      # The door the public came through: a phone call over SIP, the browser widget over WebRTC,
      # or WhatsApp text.
      CHANNEL = %w[phone web whatsapp].freeze
      # Inbound: the public reached the agent. Outbound: the agent reached out (a dial).
      DIRECTION = %w[inbound outbound].freeze
      # How a call is had: spoken in a room, or written. A web call can be either.
      MEDIUM = %w[voice text].freeze
      # Which of the two worlds a key opens, and so which world an agent is held in and a call ran
      # in. A key is issued into one; an agent registered on it and every call it takes carry that
      # one; a door claimed in one is refused to a key of the other. `sandbox` is where things are
      # written and `production` is what the public reaches — and whether a sandbox agent is one
      # PERSON's copy or the team's shared one is not this field: it is whether the key that
      # registered it names a person. Every key issued before the field existed is production.
      ENV = %w[production sandbox].freeze
      # What a console may ask of the process standing in the agent's directory, relayed by the
      # gateway: a written call to the class mounted there (chat), a simulated caller put on the
      # class it holds, its goldens and a suite of them, its knowledge folder pushed or its golden
      # asked, its memory goldens, the panel it draws beside a conversation (view), a call
      # promoted to a candidate file, the drift of the last two windows, and the reproductions a
      # broken run left on that disk. Everything else a console needs is a door of the gateway.
      DEV_VERB = %w[chat.roster chat.start chat.say chat.end view.render simulate.start goldens.roster goldens.run knowledge.roster knowledge.push knowledge.eval memory.roster memory.eval memory.extraction promote.roster promote.write drift.read reproductions.roster reproductions.read].freeze
      # Why the call is over. Who hung up, what failed before anybody could, drained: the platform
      # took the worker down (a deploy, a stop) with the call still on it, or app_detached: the
      # app holding the agent closed its socket mid-call, so nothing was rendering the prompt or
      # answering a tool — both are nobody's fault and neither is an error.
      END_REASON = %w[caller_hung_up agent_hung_up supervisor_ended transferred no_answer busy dial_failed timeout drained app_detached error].freeze
      # Whose action ended the call. platform covers timeouts, errors and a drained worker.
      ENDED_BY = %w[caller agent supervisor platform].freeze
      # What one judge answered about a finished call. Held: the rule held. Broken: it did not,
      # and the reason names the evidence. Classified: a choice or a score was answered. N/A: the
      # question did not apply. Deferred: the judge was asked and could not settle it. Skipped:
      # nobody asked it — no model, the ceiling reached, or the org's evals used up.
      SCORE_VERDICT = %w[held broken classified na deferred skipped].freeze
      # Cold: the caller is sent on with a REFER on their SIP leg and the call ends here. Warm:
      # the number is dialled into the call's own room, the agent stays on the line until the
      # other side answers and then falls silent; the call ends when either of them hangs up.
      TRANSFER_MODE = %w[cold warm].freeze
      # Which region of the prompt a block lives in: static, before the history, cached by the
      # provider; or dynamic, after the history, replaced every turn. The append-only history in
      # between is never written by the app.
      PROMPT_REGION = %w[static dynamic].freeze
      # How the knowledge base reaches the model: retrieved, the platform runs search itself when
      # the caller's turn ends; or tool, the model calls search when it decides to. Either way the
      # chunks arrive as a tool result.
      DOCS_MODE = %w[retrieved tool].freeze
      # What the platform believes the person on the line is doing right now. The states are the
      # session's own.
      USER_STATE = %w[listening speaking away].freeze
      # What the agent is doing right now, in the session's own words: warming up, waiting,
      # hearing the caller, generating, or playing audio.
      AGENT_STATE = %w[initializing idle listening thinking speaking].freeze
      # Who a participant is to the call: the person the agent serves (over SIP or the widget),
      # the agent itself, a supervisor who took a seat in the room, a listener who only hears, or
      # a second SIP leg that room.invite brought in.
      PARTICIPANT_KIND = %w[caller agent supervisor listener sip].freeze
      # What a track carries: a microphone's audio, a camera's video, or a screen share.
      TRACK_KIND = %w[audio video screen].freeze
      # Where a track comes from, as livekit's TrackSource names it, in lower case.
      TRACK_SOURCE = %w[microphone camera screen_share screen_share_audio unknown].freeze
      # Where an outside fact came from: the tenant's backend over the app socket (app), or a
      # participant's browser over the DataChannel (participant).
      EVENT_SOURCE = %w[app participant].freeze
      # Who may see a field of the app's state: everyone in the call (public), the tenant's own
      # readers (tenant, the default for a field never declared), or nobody without masking (pii).
      VISIBILITY = %w[public tenant pii].freeze
      # Which projection a sink applies before a state or an entry leaves the platform: public for
      # a participant reading its own call, tenant for the tenant's readers. The contract is
      # docs/protocol/projections.md; a client never applies one.
      PROJECTION = %w[public tenant].freeze
      # Where the call is in its life. idle before any call.* entry, which is what an agent's own
      # log looks like.
      CALL_STATUS = %w[idle ringing dialing active ended].freeze
      # Every closed list by the name the schema gave it, for a validator to look up.
      ALL = {
        "Channel" => CHANNEL,
        "Direction" => DIRECTION,
        "Medium" => MEDIUM,
        "Env" => ENV,
        "DevVerb" => DEV_VERB,
        "EndReason" => END_REASON,
        "EndedBy" => ENDED_BY,
        "ScoreVerdict" => SCORE_VERDICT,
        "TransferMode" => TRANSFER_MODE,
        "PromptRegion" => PROMPT_REGION,
        "DocsMode" => DOCS_MODE,
        "UserState" => USER_STATE,
        "AgentState" => AGENT_STATE,
        "ParticipantKind" => PARTICIPANT_KIND,
        "TrackKind" => TRACK_KIND,
        "TrackSource" => TRACK_SOURCE,
        "EventSource" => EVENT_SOURCE,
        "Visibility" => VISIBILITY,
        "Projection" => PROJECTION,
        "CallStatus" => CALL_STATUS
      }.freeze
    end
  end
end
