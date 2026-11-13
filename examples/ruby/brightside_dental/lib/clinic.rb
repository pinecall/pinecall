# frozen_string_literal: true

# The clinic's own systems, as the agents reach them: the agenda, the patients, the invoices.
# Your code, not Pinecall's: an agent's tools call whatever your business already runs on.

require "date"
require "time"

# The agenda, the patients and the invoices: a stand-in, in memory.
module Clinic
  PATIENTS = [{ id: "p-1", name: "Ana Lopez", phone: "+14155550142" }].freeze
  INVOICES = [{ id: "inv-204", patient: "p-1", amount: 120, paid: true }].freeze
  REFUNDS = [] # the requests taken while this process runs

  module_function

  # Dr. Patel keeps one time open every weekday morning.
  def free(day) = weekday?(day) ? [{ day:, time: "09:30", with: "Dr. Patel" }] : []

  def book(day, time, patient) = { id: "v-1", day:, time:, with: "Dr. Patel", patient: }

  def patient_by_phone(phone) = PATIENTS.find { |one| one[:phone] == phone }

  def invoices_of(patient) = INVOICES.select { |one| one[:patient] == patient[:id] }

  def ask_refund(invoice, reason) = REFUNDS.push({ invoice:, reason: })

  # When a visit starts, on the clinic's clock.
  def starts_at(visit) = Time.iso8601("#{visit[:day]}T#{visit[:time]}:00-08:00")

  def weekday?(day)
    (1..5).cover?(Date.iso8601(day).wday)
  rescue Date::Error
    false
  end
end
