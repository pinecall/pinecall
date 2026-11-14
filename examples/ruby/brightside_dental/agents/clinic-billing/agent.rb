# frozen_string_literal: true

# The billing desk of Brightside Dental: it takes the call the front desk passes on.

require "pinecall"
require_relative "../../lib/clinic"

# You are the billing desk of Brightside Dental. You explain charges and take refund requests.
# Say amounts in dollars. You never promise a refund: a person at the office decides it.
# An invoice says its number, its amount and whether it is paid; never say what a charge was for.
class Billing < Pinecall::Agent
  voice "cartesia", "a5136bf9-224c-4d76-b823-52bd5efcffcc" # Jameson
  takes "a question about a charge, an invoice, a payment or a refund"

  # The invoices of the patient on the call.
  state :invoices, []

  # The front desk already found the patient: what the call's agents share comes with the call.
  def on_call(call)
    patient = call.shared[:patient]
    self.invoices = Clinic.invoices_of(patient) unless patient.nil?
  end

  # Take a refund request for one invoice. The office decides it and calls back.
  tool announce: "Let me write that down."
  def ask_refund(invoice:, reason:)
    Clinic.ask_refund(invoice, reason)
    "Written down. Say the office will call back within one business day, and promise nothing else."
  end
end
