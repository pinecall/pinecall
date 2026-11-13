# frozen_string_literal: true

require "pinecall"
require_relative "../lib/clinic"

# Started by the app for every `visit.booked` an agent logs: APP.on("visit.booked", RemindVisit).
# A flow outlives the call that started it: Pinecall keeps where it stands, and wakes it. The day
# before the visit the agent calls the patient, and once more when nobody answered.
RemindVisit = Pinecall.flow("remind-visit") do |visit, step|
  # A visit booked from a web page left no number to ring: there is no reminder to place.
  next unless visit[:phone].to_s.start_with?("+")

  step.sleep_until(Clinic.starts_at(visit), before: "24h")

  instruction = "Remind #{visit[:patient]} of the visit on #{visit[:day]} at #{visit[:time]}, " \
                "and ask whether they are still coming."
  called = step.call(visit[:phone], FrontDesk, instruction:)
  unless called.answered
    step.sleep("2h")
    step.call(visit[:phone], FrontDesk, instruction:)
  end
end
RemindVisit.cancel_on("visit.cancelled") { |gone, visit| gone[:id] == visit[:id] }
