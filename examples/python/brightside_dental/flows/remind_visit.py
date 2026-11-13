"""The reminder a booked visit starts: the day before, the front desk calls the patient."""

from collections.abc import Mapping

from lib.clinic import starts_at

from pinecall import Step, flow


# Started by the app for every `visit.booked` an agent logs: app.on("visit.booked", remind_visit).
# A flow outlives the call that started it: Pinecall keeps where it stands, and wakes it. The day
# before the visit the agent calls the patient, and once more when nobody answered.
@flow("remind-visit")
async def remind_visit(visit: Mapping[str, object], step: Step) -> None:
    """Call the patient a day before the visit, and once more two hours later if nobody answers."""
    phone = str(visit["phone"])
    # A visit booked from a web page left no number to ring: there is no reminder to place.
    if not phone.startswith("+"):
        return
    await step.sleep_until(starts_at(str(visit["day"]), str(visit["time"])), before="24h")

    instruction = (
        f"Remind {visit['patient']} of the visit on {visit['day']} at {visit['time']},"
        " and ask whether they are still coming."
    )
    called = await step.call(phone, "clinic-front-desk", instruction=instruction)
    if not called.answered:
        await step.sleep("2h")
        await step.call(phone, "clinic-front-desk", instruction=instruction)


remind_visit.cancel_on("visit.cancelled", lambda gone, visit: gone["id"] == visit["id"])
