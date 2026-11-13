"""The clinic's own systems, as the agents reach them: the agenda, the patients, the invoices.

Your code, not Pinecall's: an agent's tools call whatever your business already runs on.
"""

from datetime import date, datetime
from typing import TypedDict

# `with` is a keyword in Python, so the slot is written with the call form.
Slot = TypedDict("Slot", {"day": str, "time": str, "with": str})


class Visit(Slot):
    """A slot booked: its id, and the patient's name."""

    id: str
    patient: str


class Patient(TypedDict):
    """A patient on file, found by the number they call from."""

    id: str
    name: str
    phone: str


class Invoice(TypedDict):
    """What a patient was charged, and whether it was paid."""

    id: str
    patient: str
    amount: int
    paid: bool


class Refund(TypedDict):
    """A refund asked for one invoice, for the office to decide."""

    invoice: str
    reason: str


def _weekday(day: str) -> bool:
    try:
        return date.fromisoformat(day).weekday() < 5  # noqa: PLR2004 - Monday to Friday
    except ValueError:
        return False


class Clinic:
    """The agenda, the patients and the invoices: a stand-in, in memory."""

    def __init__(self) -> None:
        """Ana Lopez is on file, with one invoice paid."""
        self.patients: list[Patient] = [{"id": "p-1", "name": "Ana Lopez", "phone": "+14155550142"}]
        self.invoices: list[Invoice] = [
            {"id": "inv-204", "patient": "p-1", "amount": 120, "paid": True}
        ]
        self.refunds: list[Refund] = []

    # Dr. Patel keeps one time open every weekday morning.
    def free(self, day: str) -> list[Slot]:
        """The open times of one day, YYYY-MM-DD."""
        return [{"day": day, "time": "09:30", "with": "Dr. Patel"}] if _weekday(day) else []

    def book(self, day: str, time: str, patient: str) -> Visit:
        """The visit booked at that time, for that patient."""
        return {"id": "v-1", "day": day, "time": time, "with": "Dr. Patel", "patient": patient}

    def patient_by_phone(self, phone: str) -> Patient | None:
        """The patient who calls from that number, or None."""
        return next((one for one in self.patients if one["phone"] == phone), None)

    def invoices_of(self, patient: str) -> list[Invoice]:
        """The invoices of the patient with that id."""
        return [one for one in self.invoices if one["patient"] == patient]

    def ask_refund(self, invoice: str, reason: str) -> None:
        """Write a refund request down; the office decides it."""
        self.refunds.append({"invoice": invoice, "reason": reason})


clinic = Clinic()


def starts_at(day: str, time: str) -> datetime:
    """When a visit starts, on the clinic's clock."""
    return datetime.fromisoformat(f"{day}T{time}:00-08:00")
