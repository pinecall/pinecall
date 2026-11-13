# frozen_string_literal: true

# Brightside Dental's voice app: one number, the team behind it, and what outlives a call.

require "pinecall"
require_relative "flows/remind_visit"

APP = Pinecall.voice_app("brightside", timezone: "America/Los_Angeles")

# One number and a team behind it: the front desk answers, and the call may pass to billing.
APP.line("+1 415 555 0134", FrontDesk, greeting: "Brightside Dental. How can I help?", team: [Billing])

# What every agent of the app is held to, and what it says when the caller goes quiet.
APP.rule("Never say an amount of money that a tool did not give you.")
APP.silence(after: "8s", say: "Are you still there?", times: 2)

# The front desk logs `visit.booked` when its `book` tool books a visit. The app hears it and
# starts that visit's reminder: a flow, which goes on after the call is over.
APP.on("visit.booked", RemindVisit)
