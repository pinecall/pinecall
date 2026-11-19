"""The callers the front desk is tested with: `pinecall simulate` phones the agent as each one."""

from pinecall import own_persona

# A test caller is who they are, what they want and how they talk; the judges read the call.
HURRIED = own_persona(
    name="hurried",
    goal="I want a cleaning this Thursday morning, the earliest time you have",
    style="short sentences, interrupts, gives my name only when asked",
    expects=["The agent should offer times from the agenda and book the one I choose."],
)

CHARGED_TWICE = own_persona(
    name="charged-twice",
    goal="I was charged twice for last month's cleaning and I want one charge back",
    style="polite, a little annoyed, has the invoice number at hand",
    expects=["The agent should pass me to billing, and never promise a refund itself."],
)
