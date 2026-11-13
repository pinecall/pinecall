"""The front desk of Brightside Dental: it reads the agenda, books, and passes a charge on."""

from typing import ClassVar

from lib.clinic import Slot, Visit, clinic
from typing_extensions import override

from pinecall import Agent, CallWorld, judges, llm, personas, stt, tool, voice

from .harness import CHARGED_TWICE, HURRIED, OFFERS_A_REAL_TIME


@stt("deepgram/flux-general-en")
@llm("google/gemini-3.5-flash-lite")
@voice("cartesia", "f786b574-daa5-4673-aa0c-cbe3e8534c02")  # Katie
class FrontDesk(Agent):
    """You are the front desk of Brightside Dental. You book, move and explain visits.
    Short sentences. Offer at most two times. Never say a time the agenda did not give you.
    Before you book a time, ask the caller's name. Never book without it.
    """

    takes = "booking, moving or asking about a visit"
    judges: ClassVar = judges(on=["consent", "grounded"], own=[OFFERS_A_REAL_TIME])
    personas: ClassVar = personas(own=[HURRIED, CHARGED_TWICE])

    # The times last read from the agenda: the only ones the agent may offer.
    slots: list[Slot] = []  # noqa: RUF012 - the value each call opens with, copied for each one

    # The patient is found once, as the call arrives, and shared with whoever takes the call next.
    @override
    def on_call(self, call: CallWorld) -> None:
        self.call.shared["patient"] = clinic.patient_by_phone(call.contact)

    @tool(announce="Let me check the agenda.")
    def free_slots(self, day: str) -> list[Slot] | str:
        """The open times of one day. `day` is YYYY-MM-DD."""
        self.slots = clinic.free(day)
        if not self.slots:
            return "Nothing is open that day. Say just that, and ask about another day."
        return self.slots

    @tool
    def book(self, day: str, time: str, name: str) -> Visit | str:
        """Book one of the times free_slots returned, once the caller chose it and gave their name."""
        offered = any(slot["day"] == day and slot["time"] == time for slot in self.slots)
        if not offered:
            return "That time did not come from the agenda. Call free_slots for that day first."
        visit = clinic.book(day, time, name)
        # A line on the call's log, by its name: the app hears it and starts the visit's reminder (app.py).
        self.log("visit.booked", {**visit, "phone": self.call.contact})
        return visit
