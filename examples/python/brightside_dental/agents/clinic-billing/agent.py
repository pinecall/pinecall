"""The billing desk of Brightside Dental: it takes the call the front desk passes on."""

from lib.clinic import Invoice, clinic
from typing_extensions import override

from pinecall import Agent, CallWorld, tool, voice


@voice("cartesia", "a5136bf9-224c-4d76-b823-52bd5efcffcc")  # Jameson
class Billing(Agent):
    """You are the billing desk of Brightside Dental. You explain charges and take refund requests.
    Say amounts in dollars. You never promise a refund: a person at the office decides it.
    """

    takes = "a question about a charge, an invoice, a payment or a refund"

    # The invoices of the patient on the call.
    invoices: list[Invoice] = []  # noqa: RUF012 - the value each call opens with, copied for each one

    # The front desk already found the patient: what the call's agents share comes with the call.
    @override
    def on_call(self, call: CallWorld) -> None:
        match self.call.shared.get("patient"):
            case {"id": str() as patient}:
                self.invoices = clinic.invoices_of(patient)
            case _:
                pass

    @tool(announce="Let me write that down.")
    def ask_refund(self, invoice: str, reason: str) -> str:
        """Take a refund request for one invoice. The office decides it and calls back."""
        clinic.ask_refund(invoice, reason)
        return "Written down. Say the office will call back within one business day, and promise nothing else."
