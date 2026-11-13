# frozen_string_literal: true

# The front desk of Brightside Dental: it reads the agenda, books, and passes a charge on.

require "pinecall"
require_relative "../../lib/clinic"
require_relative "harness"

# You are the front desk of Brightside Dental. You book, move and explain visits.
# Short sentences. Offer at most two times. Never say a time the agenda did not give you.
# Before you book a time, ask the caller's name. Never book without it.
class FrontDesk < Pinecall::Agent
  stt "deepgram/flux-general-en"
  llm "google/gemini-3.5-flash-lite"
  voice "cartesia", "f786b574-daa5-4673-aa0c-cbe3e8534c02" # Katie
  takes "booking, moving or asking about a visit"
  judges on: %w[consent grounded], own: [OFFERS_A_REAL_TIME]
  personas own: [HURRIED, CHARGED_TWICE]

  # The times last read from the agenda: the only ones the agent may offer.
  state :slots, []

  # The patient is found once, as the call arrives, and shared with whoever takes the call next.
  def on_call(call)
    call.shared[:patient] = Clinic.patient_by_phone(call.contact)
  end

  # The open times of one day. `day` is YYYY-MM-DD.
  tool announce: "Let me check the agenda."
  def free_slots(day:)
    self.slots = Clinic.free(day)
    return "Nothing is open that day. Say just that, and ask about another day." if slots.empty?

    slots
  end

  # Book one of the times free_slots returned, once the caller chose it and gave their name.
  tool
  def book(day:, time:, name:)
    offered = slots.any? { |slot| slot[:day] == day && slot[:time] == time }
    return "That time did not come from the agenda. Call free_slots for that day first." unless offered

    visit = Clinic.book(day, time, name)
    # A line on the call's log, by its name: the app hears it and starts the visit's reminder (app.rb).
    log("visit.booked", visit.merge(phone: call.contact))
    visit
  end
end
