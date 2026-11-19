"""The front desk's own judge."""

from pinecall import own_judge

# A judge asks one question of every call when it ends, and answers held or broken.
# `consent` and `grounded` are Pinecall's; this one is the clinic's own.
OFFERS_A_REAL_TIME = own_judge(
    name="offers-a-real-time",
    asks="Did every time the agent offered come from a free_slots result of this call?",
    reads=["evidence"],
)
