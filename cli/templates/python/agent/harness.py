"""The judges of {{Title}}'s own, as code: imported by agent.py into judges(own=…)."""

# A judge of the agent's own asks one question of every call at hang-up, answered held or broken; `pinecall judges try
# <name> --last 5` asks it of the last calls before you keep it. One looks like this, with `own_judge` imported from pinecall:
#   MESSAGE_TAKEN = own_judge(name="message-taken", asks="Did the agent write the message down before saying goodbye?")
