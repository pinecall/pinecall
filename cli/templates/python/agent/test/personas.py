"""The callers {{Title}} is tested with: every own_persona this file defines is one of the agent's own, and ON names Pinecall's."""

from pinecall import own_persona

# Pinecall's callers this agent is tested with. `pinecall simulate` phones the agent as each one, and as each of its own.
ON = ["in-a-hurry", "wrong-number"]

# Calls from the street, in a rush, with one thing to leave.
HURRIED = own_persona(
    name="hurried",
    about="Calls from the street, in a rush, with one thing to leave",
    goal="leave a message for the business: I am Ana García and the delivery for tomorrow has to come after 4 pm",
    style="short sentences, interrupts, gives one fact at a time, asks twice whether the message is written down",
    facts={"their name": "Ana García", "their phone": "600 000 001"},
    expects=[
        "The agent should write the message down with the caller's name and what it is about.",
        "The agent should not promise when the business will call back.",
    ],
    behavior={"interrupts": 0.3, "pause_s": 1},
)
