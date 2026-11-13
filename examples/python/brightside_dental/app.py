"""Brightside Dental's voice app: one number, the team behind it, and what outlives a call."""

from flows.remind_visit import remind_visit

from pinecall import voice_app

app = voice_app("brightside", timezone="America/Los_Angeles")

# One number and a team behind it: the front desk answers, and the call may pass to billing.
# An agent is named by its slug, its folder's name under agents/.
app.line(
    "+1 415 555 0134",
    "clinic-front-desk",
    greeting="Brightside Dental. How can I help?",
    team=["clinic-billing"],
)

# What every agent of the app is held to, and what it says when the caller goes quiet.
app.rule("Never say an amount of money that a tool did not give you.")
app.silence(after="8s", say="Are you still there?", times=2)

# The front desk logs `visit.booked` when its `book` tool books a visit. The app hears it and
# starts that visit's reminder: a flow, which goes on after the call is over.
app.on("visit.booked", remind_visit)
